"""广播 HTTP 接口

- ``POST /api/broadcast``：鉴权后受理一次广播，立即返回 202 与广播 id，
  实际发送在后台任务里进行（一次群发动辄几分钟，不能让调用方的 HTTP 请求一直挂着）；
- ``GET /api/broadcast/targets``：列出可广播的群；
- ``GET /api/broadcast/{broadcast_id}``：查询某次广播的状态与逐群结果。

鉴权设计见 :func:`get_broadcast_principal`，配置项见 ``config.py`` 与
``.env.template``；完整说明见 ``docs/plugins/broadcast.md``。
"""

import asyncio
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Optional, Union, cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from nonebot import get_app
from nonebot.adapters import Bot
from nonebot.log import logger
from nonebot_plugin_larkuid.rate_limit import SlidingWindowRateLimiter
from nonebot_plugin_larkuid.session import authenticate
from pydantic import BaseModel

from .__main__ import get_available_groups, get_plugin_data, set_latest_broadcast_content
from .config import config
from .groups import list_group_snapshots
from .message import MAX_BUTTONS, BroadcastButton
from .models import BROADCAST_STATUS_QUEUED
from .push import (
    BroadcastEventSnapshot,
    BroadcastRecordSnapshot,
    create_broadcast_record,
    find_inflight_broadcast,
    get_broadcast_by_request_id,
    get_broadcast_record,
    get_broadcast_stats,
    list_broadcast_events,
    run_broadcast,
)

app = cast("FastAPI", get_app())

IDEMPOTENCY_HEADER = "Idempotency-Key"
# 幂等键只允许可安全放进 header / 日志的字符
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# 同一条 HTTP 广播的发送任务：持有强引用，避免任务被 GC
_BACKGROUND_TASKS: set[asyncio.Task] = set()
# 「同一时间只允许一次广播」的检查与占位需要原子化
_ADMISSION_LOCK = asyncio.Lock()
_rate_limiter: Optional[SlidingWindowRateLimiter] = None


@dataclass(frozen=True)
class BroadcastPrincipal:
    """一次成功鉴权的调用方"""

    # 限流维度，例如 ``token:ci`` / ``user:10001``
    name: str
    # 写进广播记录的调用方标识，例如 ``api:ci`` / QQ 号
    submitter: str
    # token / session，仅用于日志排查
    source: str


@dataclass(frozen=True)
class NormalizedRequest:
    """通过校验后的请求内容"""

    content: str
    buttons: Optional[list[BroadcastButton]]
    targets: Optional[list[str]]
    dry_run: bool


class BroadcastButtonInput(BaseModel):
    label: str
    text: str


class BroadcastRequest(BaseModel):
    """``POST /api/broadcast`` 的请求体"""

    content: str
    # 不填表示向所有启用的群广播；填了就只发这些群（可用 group_qq_number / group_openid）
    targets: Optional[list[Union[str, int]]] = None
    # 不填表示沿用 bcsu 里配置的按钮；显式传 [] 表示这次不带按钮
    buttons: Optional[list[BroadcastButtonInput]] = None
    # 只校验内容与目标群，不真正发送
    dry_run: bool = False


def _extract_bearer(request: Request) -> str:
    authorization = request.headers.get("Authorization") or ""
    scheme, _, credential = authorization.partition(" ")
    credential = credential.strip()
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization: Bearer <token> 凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credential


def _match_api_token(credential: str) -> Optional[str]:
    """在配置的 API Token 里找匹配项，返回 token 名称

    按字节做常数时间比较；配置里留空的 token 视为未配置。即使命中也不提前返回，
    避免通过响应时间推断命中的是第几个 token。
    """
    matched: Optional[str] = None
    credential_bytes = credential.encode("utf-8")
    for name, token in config.broadcast_api_tokens.items():
        token = token.strip()
        if not token:
            continue
        if hmac.compare_digest(credential_bytes, token.encode("utf-8")) and matched is None:
            matched = name
    return matched


async def get_broadcast_principal(request: Request) -> BroadcastPrincipal:
    """广播接口鉴权：API Token 或超管 Web 会话

    先尝试 ``BROADCAST_API_TOKENS`` 里配置的机器凭据（``Authorization: Bearer <token>``），
    再退化到 Moonlark Web 会话——会话必须已激活，且用户属于 ``SUPERUSERS``。

    不支持的凭据来源：query string（会进反代日志与 Referer）、自定义 header。
    """
    credential = _extract_bearer(request)
    token_name = _match_api_token(credential)
    if token_name is not None:
        return BroadcastPrincipal(name=f"token:{token_name}", submitter=f"api:{token_name}", source="token")

    try:
        context = await authenticate(request)
    except HTTPException as error:
        if error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="凭据无效：既不是已配置的广播 API Token，也不是有效的 Web 会话",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    if context.user_id not in config.superusers:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级用户可以通过 Web 会话触发广播")
    return BroadcastPrincipal(name=f"user:{context.user_id}", submitter=context.user_id, source="session")


def _get_rate_limiter() -> Optional[SlidingWindowRateLimiter]:
    """按当前配置构造（或复用）进程内限流器；配额 <=0 时返回 None 表示不限流"""
    global _rate_limiter
    quota = config.broadcast_api_rate_limit
    window = config.broadcast_api_rate_window
    if quota <= 0 or window <= 0:
        return None
    if _rate_limiter is None or (_rate_limiter.times, _rate_limiter.window_seconds) != (quota, window):
        _rate_limiter = SlidingWindowRateLimiter(quota, window)
    return _rate_limiter


async def enforce_broadcast_rate_limit(
    principal: BroadcastPrincipal = Depends(get_broadcast_principal),
) -> BroadcastPrincipal:
    """鉴权 + 按调用方限流，返回调用方身份"""
    limiter = _get_rate_limiter()
    if limiter is not None:
        await limiter.check(principal.name)
    return principal


def _normalize_request(payload: BroadcastRequest) -> NormalizedRequest:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content 不能为空")
    max_length = config.broadcast_api_max_content_length
    if len(content) > max_length:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"content 超过 {max_length} 字符上限")

    buttons: Optional[list[BroadcastButton]] = None
    if payload.buttons is not None:
        if len(payload.buttons) > MAX_BUTTONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"buttons 最多 {MAX_BUTTONS} 个")
        buttons = []
        for index, button in enumerate(payload.buttons, start=1):
            label = button.label.strip()
            text = button.text.strip()
            if not label or not text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"第 {index} 个按钮的 label 与 text 都不能为空",
                )
            buttons.append(BroadcastButton(label=label, text=text))

    targets: Optional[list[str]] = None
    if payload.targets is not None:
        targets = []
        seen: set[str] = set()
        for raw_target in payload.targets:
            target = str(raw_target).strip()
            if not target:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="targets 中不能包含空值")
            if len(target) > 128:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="targets 中存在过长的群标识")
            if target not in seen:
                seen.add(target)
                targets.append(target)
        if not targets:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="targets 不能是空列表；不限制目标群时请省略该字段",
            )

    return NormalizedRequest(content=content, buttons=buttons, targets=targets, dry_run=payload.dry_run)


def _get_idempotency_key(request: Request) -> Optional[str]:
    raw_key = request.headers.get(IDEMPOTENCY_HEADER)
    if raw_key is None:
        return None
    key = raw_key.strip()
    if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key 只允许 1-64 个字母、数字或 _ . : -",
        )
    return key


def _request_fingerprint(content: str, buttons: list[BroadcastButton], targets: Optional[list[str]]) -> str:
    payload = json.dumps(
        {"content": content, "buttons": buttons, "targets": targets},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _resolve_targets(targets: Optional[list[str]]) -> dict[str, list[Bot]]:
    """把请求里的目标群解析成真实的发送目标；不指定时使用全部启用群"""
    available = await get_available_groups()
    if targets is None:
        return available
    missing = [target for target in targets if target not in available]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "以下群不存在、未开启广播或当前不可达", "targets": missing},
        )
    return {target: available[target] for target in targets}


def _record_payload(record: BroadcastRecordSnapshot) -> dict:
    return {
        "broadcast_id": record.id,
        "status": record.status,
        "total": record.total,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _event_payload(event: BroadcastEventSnapshot) -> dict:
    return {
        "group_key": event.group_key,
        "group_openid": event.group_openid,
        "bot_id": event.bot_id,
        "adapter": event.adapter,
        "mode": event.mode,
        "status": event.status,
        "error": event.error,
        "passive_msg_id": event.passive_msg_id,
        "sent_at": event.sent_at.isoformat() if event.sent_at else None,
    }


async def _run_scheduled_broadcast(
    broadcast_id: int,
    groups: dict[str, list[Bot]],
    content: str,
    buttons: list[BroadcastButton],
    principal: BroadcastPrincipal,
) -> None:
    """后台发送任务：把已受理的广播真正发出去"""
    logger.info(f"广播 #{broadcast_id} 开始发送：{principal.submitter}（{principal.source}），目标 {len(groups)} 群")
    try:
        # 与 bcsu submit 保持一致，让 /bc 能看到最后一次广播；这里失败不影响发送
        await set_latest_broadcast_content(content)
    except Exception:
        logger.warning(f"广播 #{broadcast_id} 更新 /bc 展示内容失败")
    try:
        result = await run_broadcast(broadcast_id, groups, content, buttons)
    except Exception:
        # run_broadcast 已把记录标为 failed，这里只吞掉异常避免任务告警
        logger.exception(f"广播 #{broadcast_id} 发送流程异常")
        return
    logger.info(
        f"广播 #{broadcast_id} 发送结束：成功 {result.sent}，失败 {result.failed}，等待被动补发 {result.pending}",
    )


@app.post("/api/broadcast", status_code=status.HTTP_202_ACCEPTED)
async def create_broadcast(
    payload: BroadcastRequest,
    request: Request,
    response: Response,
    principal: BroadcastPrincipal = Depends(enforce_broadcast_rate_limit),
) -> dict:
    """受理一次广播（需要 API Token 或超管 Web 会话）

    - 幂等：带 ``Idempotency-Key`` 时，同一个键重复提交只会产生一次广播；
    - 单并发：已有广播正在发送时返回 409，避免两次群发交叠；
    - 限流：默认每个调用方每分钟 5 次；
    - ``dry_run=true`` 只校验并返回目标群，不发送。
    """
    normalized = _normalize_request(payload)
    buttons = normalized.buttons
    if buttons is None:
        buttons = (await get_plugin_data())["buttons"]
    idempotency_key = _get_idempotency_key(request)
    request_hash = _request_fingerprint(normalized.content, buttons, normalized.targets)

    if idempotency_key is not None:
        existing = await get_broadcast_by_request_id(idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key 已用于另一次内容不同的广播",
                )
            return {**_record_payload(existing), "idempotent": True}

    groups = await _resolve_targets(normalized.targets)

    if normalized.dry_run:
        response.status_code = status.HTTP_200_OK
        return {"dry_run": True, "total": len(groups), "targets": list(groups)}

    async with _ADMISSION_LOCK:
        # 并发请求可能都通过了前面的幂等检查，拿到锁后再确认一次
        if idempotency_key is not None:
            existing = await get_broadcast_by_request_id(idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency-Key 已用于另一次内容不同的广播",
                    )
                return {**_record_payload(existing), "idempotent": True}

        inflight = await find_inflight_broadcast()
        if inflight is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"广播 #{inflight.id} 仍在进行中，请等待它结束或改用幂等键查询",
                headers={"Retry-After": "30"},
            )

        broadcast_id = await create_broadcast_record(
            normalized.content,
            buttons,
            principal.submitter,
            request_id=idempotency_key,
            request_hash=request_hash,
            total=len(groups),
            status=BROADCAST_STATUS_QUEUED,
        )
        task = asyncio.create_task(
            _run_scheduled_broadcast(broadcast_id, groups, normalized.content, buttons, principal),
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

    return {
        "broadcast_id": broadcast_id,
        "status": BROADCAST_STATUS_QUEUED,
        "total": len(groups),
        "targets": list(groups),
        "idempotent": False,
    }


@app.get("/api/broadcast/targets")
async def list_broadcast_targets(principal: BroadcastPrincipal = Depends(get_broadcast_principal)) -> dict:
    """列出群列表与每个群当前的广播可用性（需要 API Token 或超管 Web 会话）"""
    data = await get_plugin_data()
    disabled = set(data["disabled_groups"])
    snapshots = await list_group_snapshots()
    available = await get_available_groups()

    groups = []
    for snapshot in snapshots:
        identifiers = (snapshot.group_key, snapshot.group_qq_number, snapshot.group_openid)
        target = next((identifier for identifier in identifiers if identifier and identifier in available), None)
        groups.append(
            {
                "group_key": snapshot.group_key,
                "group_qq_number": snapshot.group_qq_number,
                "group_openid": snapshot.group_openid,
                "target": target,
                "enabled": not any(identifier is not None and identifier in disabled for identifier in identifiers),
                "available": target is not None,
                "allow_proactive_msg": snapshot.allow_proactive_msg,
                "last_message_at": snapshot.last_message_at.isoformat() if snapshot.last_message_at else None,
            },
        )
    return {"total": len(groups), "groups": groups}


@app.get("/api/broadcast/{broadcast_id}")
async def get_broadcast_status(
    broadcast_id: int,
    principal: BroadcastPrincipal = Depends(get_broadcast_principal),
) -> dict:
    """查询广播状态与逐群推送结果（需要 API Token 或超管 Web 会话）"""
    record = await get_broadcast_record(broadcast_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="广播记录不存在")
    stats = await get_broadcast_stats(broadcast_id)
    events = await list_broadcast_events(broadcast_id)
    return {
        "broadcast_id": record.id,
        "status": record.status,
        "total": record.total,
        "submitter": record.submitter,
        "request_id": record.request_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "stats": stats,
        "events": [_event_payload(event) for event in events],
    }
