import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select
from sqlalchemy.exc import NoResultFound

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.user.base import MoonlarkUser
from .config import config
from .models import SessionData

# 活跃时间戳与过期顺延的最小写入间隔：避免每个请求都写库
ACTIVITY_FLUSH_INTERVAL_SECONDS = 60


def utcnow() -> datetime:
    """统一的会话时间基准：UTC naive（与数据库 DateTime 列一致）。

    旧代码混用服务器本地时间，跨时区部署时到期判断会偏移；新代码全部走 UTC。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_user_agent(request: Request) -> str:
    return request.headers.get("User-Agent") or ""


def get_device(request: Request) -> str:
    """设备描述（原始 UA 截断），仅用于设备管理列表展示。"""
    return get_user_agent(request)[:256]


def get_identifier(request: Request) -> str:
    """会话标识：仅绑定 User-Agent。

    旧版同时绑定客户端 IP，移动网络切换、NAT 出口变化等正常场景都会被强制下线；
    UA 才是「同一台浏览器」的稳定信号，IP 不再参与校验。
    """
    return hashlib.sha256(get_user_agent(request).encode()).hexdigest()


def get_legacy_identifier(request: Request) -> str:
    """旧版标识（UA + IP），用于兼容升级前签发的存量会话，避免全员掉线。"""
    legacy = f"{request.headers.get('User-Agent')}{request.client.host if request.client else ''}"
    return hashlib.sha256(legacy.encode()).hexdigest()


@dataclass
class AuthContext:
    """一次成功鉴权的结果。"""

    session_id: str
    user_id: str
    # 会话是否仍处于待激活状态（allow_pending=True 时才可能为 True）
    pending: bool


class InvalidSessionError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED)


def _parse_bearer_session_id(request: Request) -> str:
    authorization = request.headers.get("Authorization") or ""
    if not authorization.startswith("Bearer "):
        raise InvalidSessionError()
    session_id = authorization[len("Bearer ") :].strip()
    if not session_id:
        raise InvalidSessionError()
    return session_id


async def _evict_excess_sessions(user_id: str, keep: int) -> None:
    """按用户挤掉最旧的会话，为新建会话腾出位置（并发上限）。"""
    if keep < 0:
        keep = 0
    async with get_session() as session:
        old = (
            await session.scalars(
                # MySQL 不支持 NULLS FIRST，用布尔表达式把无创建时间的存量行视为最旧优先挤掉
                select(SessionData)
                .where(SessionData.user_id == user_id)
                .order_by(SessionData.created_at.is_(None).desc(), SessionData.created_at.asc())
                .limit(keep)
            )
        ).all()
        for item in old:
            await session.delete(item)
        await session.commit()


async def create_session(user_id: str, request: Request, retention_days: int) -> tuple[str, str]:
    days = max(1, min(retention_days, config.session_max_lifetime_days))
    await _evict_excess_sessions(user_id, config.max_sessions_per_user - 1)
    session_id = uuid.uuid4().hex
    async with get_session() as session:
        session.add(
            SessionData(
                session_id=session_id,
                user_id=user_id,
                identifier=get_identifier(request),
                expiration_time=utcnow() + timedelta(days=days),
                activate_code=(activate_code := str(uuid.uuid4()).split("-")[0]),
                created_at=utcnow(),
                device=get_device(request),
            )
        )
        await session.commit()
    return session_id, activate_code


async def _apply_activity(data: SessionData, now: datetime) -> None:
    """滑动过期：活跃时把 expiration_time 向后顺延 idle 天，但不超过创建时间 + 绝对上限。

    与 last_active_at 共用同一个写入节流窗口；存量行没有 created_at 时不套用绝对上限。
    """
    last = data.last_active_at or data.created_at
    if last is not None and (now - last).total_seconds() < ACTIVITY_FLUSH_INTERVAL_SECONDS:
        return
    idle_expiry = now + timedelta(days=config.session_idle_days)
    if data.created_at is not None:
        absolute_expiry = data.created_at + timedelta(days=config.session_max_lifetime_days)
        idle_expiry = min(idle_expiry, absolute_expiry)
    if idle_expiry > (data.expiration_time or idle_expiry):
        data.expiration_time = idle_expiry
    data.last_active_at = now


async def authenticate(request: Request, *, allow_pending: bool = False) -> AuthContext:
    """核心鉴权门：校验 Bearer 会话并维护滑动过期，失败抛 401。

    - 会话不存在 / 已过期 / 设备标识不匹配：删除会话并抛 401；
    - 待激活会话默认拒绝（`allow_pending=True` 供登录等待轮询使用）；
    - 校验通过时按节流间隔顺延 expiration_time 并刷新 last_active_at。
    """
    session_id = _parse_bearer_session_id(request)
    async with get_session() as session:
        try:
            data = await session.get_one(SessionData, session_id)
        except NoResultFound:
            raise InvalidSessionError() from None
        now = utcnow()
        identifier_matched = data.identifier in (get_identifier(request), get_legacy_identifier(request))
        expired = data.expiration_time is not None and now >= data.expiration_time
        if not identifier_matched or expired:
            logger.debug(f"会话 {session_id} 已失效（{'标识不匹配' if not identifier_matched else '已过期'}），清理")
            await session.delete(data)
            await session.commit()
            raise InvalidSessionError()
        if data.activate_code is not None and not allow_pending:
            raise InvalidSessionError()
        context = AuthContext(
            session_id=data.session_id, user_id=data.user_id, pending=data.activate_code is not None
        )
        await _apply_activity(data, now)
        await session.commit()
        return context


async def _get_user_id(request: Request) -> str:
    return (await authenticate(request)).user_id


def get_user_id(default: Optional[str] = None):  # noqa: ANN201 保持原有返回形态
    if default is None:
        return Depends(_get_user_id)
    else:

        async def _(request: Request) -> str:
            try:
                return await _get_user_id(request)
            except HTTPException:
                return default

        return Depends(_)


def get_current_session():
    """FastAPI 依赖：要求已激活的会话，返回 AuthContext（供登出 / 设备管理使用）。"""

    async def _(request: Request) -> AuthContext:
        return await authenticate(request)

    return Depends(_)


async def _get_existing_user(user_id: str = get_user_id()) -> MoonlarkUser:
    try:
        return await get_user(user_id)
    except NoResultFound:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


async def _get_user_data(user_id: str = get_user_id()) -> MoonlarkUser:
    return await get_user(user_id)


async def _get_registered_user(user_data: MoonlarkUser = Depends(_get_existing_user)) -> MoonlarkUser:
    if not user_data.is_registered():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user_data


def get_user_data(registered: bool = False) -> MoonlarkUser:
    if registered:
        return Depends(_get_registered_user)
    return Depends(_get_user_data)


@scheduler.scheduled_job("cron", day="*", id="remove_session")
async def _remove_expired_sessions() -> None:
    """每日清理已过期的会话。"""
    async with get_session() as session:
        await session.execute(delete(SessionData).where(SessionData.expiration_time <= utcnow()))
        await session.commit()


@scheduler.scheduled_job("cron", minute="*/5", id="remove_unused_session")
async def _remove_unused_sessions() -> None:
    """定期清理超时未激活的会话。

    替代旧版「登录时挂 asyncio.sleep 任务」的做法——进程重启后任务即丢失，
    未激活会话只能等到期后才被每日任务回收；改为扫 created_at 不依赖进程存活。
    存量行没有 created_at，仍由每日过期清理兜底。
    """
    boundary = utcnow() - timedelta(seconds=config.unused_session_remove_delay)
    async with get_session() as session:
        result = await session.scalars(
            select(SessionData).where(
                SessionData.activate_code.is_not(None),
                SessionData.created_at.is_not(None),
                SessionData.created_at <= boundary,
            )
        )
        stale = result.all()
        if stale:
            logger.info(f"清理 {len(stale)} 个超时未激活的会话")
        for item in stale:
            await session.delete(item)
        await session.commit()
