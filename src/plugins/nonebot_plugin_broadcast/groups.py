"""bc 自己维护的群列表

QQ 官方机器人没有“获取群列表”的接口，旧实现只能靠 ``GroupBind`` 猜测群聊。
这里改为在每次收到群消息时把群写进 ``BroadcastGroup`` 表，并顺带补齐
``GET /v2/groups/{group_openid}/bot_state`` 的信息（白名单接口，可能不可用）。
"""

import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from nonebot import get_bots
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as V11Bot, GroupMessageEvent
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.log import logger
from nonebot.message import event_preprocessor
from nonebot_plugin_bots.models import GroupBind
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BroadcastGroup

# bot_state 是低频变化的信息，同一个群最多每小时刷新一次（接口有频率限制，
# 且白名单机器人之外调用只会得到 11253）
BOT_STATE_REFRESH_SECONDS = 3600


@dataclass
class GroupSnapshot:
    """群列表的一行快照（脱离 ORM Session 后仍可安全读取）"""

    group_key: str
    group_qq_number: Optional[str]
    group_openid: Optional[str]
    last_message_at: Optional[datetime]
    bot_state_checked_at: Optional[datetime]
    allow_proactive_msg: Optional[bool]
    recv_msg_setting: Optional[str]
    member_role: Optional[str]
    member_openid: Optional[str]
    joined_at: Optional[datetime]


def _snapshot(row: BroadcastGroup) -> GroupSnapshot:
    return GroupSnapshot(
        group_key=row.group_key,
        group_qq_number=row.group_qq_number,
        group_openid=row.group_openid,
        last_message_at=row.last_message_at,
        bot_state_checked_at=row.bot_state_checked_at,
        allow_proactive_msg=row.allow_proactive_msg,
        recv_msg_setting=row.recv_msg_setting,
        member_role=row.member_role,
        member_openid=row.member_openid,
        joined_at=row.joined_at,
    )


async def resolve_group_key(group_id: str) -> str:
    """把群标识归一化为广播开关使用的键

    OB11 群号保持原样；QQ 官方的 group_openid 若已与群号绑定则使用群号，
    这样同一个物理群在两种协议下的开关状态一致。
    """
    group_id = group_id.removeprefix("qq_")
    if group_id.isdigit():
        return group_id
    async with get_session() as session:
        bind = await session.scalar(select(GroupBind).where(GroupBind.group_openid == group_id))
    if bind is not None and bind.group_qq_number:
        return bind.group_qq_number
    return group_id


async def get_event_group_key(event: Event) -> Optional[str]:
    """获取事件所在群的广播开关键，非群聊事件返回 None"""
    group_qq_number, group_openid = await get_group_ids_from_event(event)
    if group_qq_number:
        return group_qq_number
    if group_openid:
        return await resolve_group_key(group_openid)
    return None


async def _lookup_bind(group_qq_number: Optional[str], group_openid: Optional[str]) -> Optional[GroupBind]:
    async with get_session() as session:
        if group_qq_number:
            bind = await session.scalar(select(GroupBind).where(GroupBind.group_qq_number == group_qq_number))
            if bind is not None:
                return bind
        if group_openid:
            return await session.scalar(select(GroupBind).where(GroupBind.group_openid == group_openid))
    return None


async def get_group_ids_from_event(event: Event) -> tuple[Optional[str], Optional[str]]:
    """从群消息事件中取出 (群 QQ 号, 群 openid)，并尽量用 GroupBind 补齐另一侧"""
    group_qq_number: Optional[str] = None
    group_openid: Optional[str] = None
    if isinstance(event, GroupMessageEvent):
        group_qq_number = str(event.group_id)
    elif isinstance(event, GroupMessageCreateEvent):
        group_openid = event.group_openid
    else:
        return None, None

    bind = await _lookup_bind(group_qq_number, group_openid)
    if bind is not None:
        group_qq_number = bind.group_qq_number or group_qq_number
        group_openid = bind.group_openid or group_openid
    return group_qq_number, group_openid


def _group_key(group_qq_number: Optional[str], group_openid: Optional[str]) -> str:
    return group_qq_number or group_openid or ""


async def _get_or_create_group(
    session: AsyncSession,
    group_qq_number: Optional[str],
    group_openid: Optional[str],
    seen_at: Optional[datetime] = None,
) -> BroadcastGroup:
    """按归一化键取群记录，不存在则创建，并补齐已知的另一侧标识"""
    key = _group_key(group_qq_number, group_openid)
    row = await session.get(BroadcastGroup, key) if key else None
    if row is None and group_qq_number:
        row = await session.scalar(select(BroadcastGroup).where(BroadcastGroup.group_qq_number == group_qq_number))
    if row is None and group_openid:
        row = await session.scalar(select(BroadcastGroup).where(BroadcastGroup.group_openid == group_openid))
    if row is None:
        row = BroadcastGroup(group_key=key, group_qq_number=group_qq_number, group_openid=group_openid)
        session.add(row)
    else:
        if group_qq_number and not row.group_qq_number:
            row.group_qq_number = group_qq_number
        if group_openid and not row.group_openid:
            row.group_openid = group_openid
        normalized_key = _group_key(row.group_qq_number, row.group_openid)
        if normalized_key and normalized_key != row.group_key:
            # 之后才完成 GroupBind 时，把记录从 openid 键迁移到群号键
            row.group_key = normalized_key
    if seen_at is not None:
        row.last_message_at = seen_at
    return row


async def record_group_message(
    group_qq_number: Optional[str],
    group_openid: Optional[str],
    seen_at: Optional[datetime] = None,
) -> str:
    """写入/更新群列表，返回归一化后的群键"""
    async with get_session() as session:
        row = await _get_or_create_group(session, group_qq_number, group_openid, seen_at)
        key = row.group_key
        await session.commit()
    return key


async def sync_ob11_groups() -> dict[str, list[Bot]]:
    """把 OneBot V11 的实时群列表同步进表，并返回「群号 -> 可发送的 bot」"""
    groups: dict[str, list[Bot]] = {}
    async with get_session() as session:
        for bot in get_bots().values():
            if not isinstance(bot, V11Bot):
                continue
            try:
                group_list = await bot.get_group_list()
            except Exception:
                logger.warning(f"获取 {bot.self_id} 的群列表失败：{traceback.format_exc()}")
                continue
            for group in group_list:
                group_id = str(group["group_id"])
                groups.setdefault(group_id, []).append(bot)
                await _get_or_create_group(session, group_id, None)
        await session.commit()
    return groups


async def sync_bound_groups() -> None:
    """把 GroupBind 里登记的群补进群列表（群里还没发过消息时也能被广播到）"""
    async with get_session() as session:
        binds = (await session.scalars(select(GroupBind))).all()
        if not binds:
            return
        for bind in binds:
            if not bind.group_qq_number and not bind.group_openid:
                continue
            await _get_or_create_group(session, bind.group_qq_number, bind.group_openid)
        await session.commit()


async def get_group_snapshot(group_key: str) -> Optional[GroupSnapshot]:
    """读取一个群的快照"""
    async with get_session() as session:
        row = await session.get(BroadcastGroup, group_key)
        return _snapshot(row) if row is not None else None


async def list_group_snapshots() -> list[GroupSnapshot]:
    """列出群列表（按最后收到消息时间倒序，从未收到消息的排在最后）"""
    async with get_session() as session:
        rows = (await session.scalars(select(BroadcastGroup))).all()
        snapshots = [_snapshot(row) for row in rows]
    snapshots.sort(key=lambda item: item.last_message_at or datetime.min, reverse=True)
    return snapshots


def _pick_qq_bot(bot: Optional[Bot] = None) -> Optional[QQBot]:
    if isinstance(bot, QQBot):
        return bot
    for candidate in get_bots().values():
        if isinstance(candidate, QQBot):
            return candidate
    return None


async def refresh_group_bot_state(group_key: str, bot: Optional[Bot] = None, force: bool = False) -> Optional[bool]:
    """刷新并返回群记录里的 ``allow_proactive_msg``

    该接口只对白名单机器人开放；调用失败时保留上一次取到的值（可能一直是
    ``None``），并记录本次检查时间，避免每条消息都去打一个不可用的接口。

    Returns:
        ``allow_proactive_msg``；群不存在或没有 openid 时返回 ``None``。
    """
    snapshot = await get_group_snapshot(group_key)
    if snapshot is None or not snapshot.group_openid:
        return None
    now = datetime.now()
    if not force and snapshot.bot_state_checked_at is not None:
        if now - snapshot.bot_state_checked_at < timedelta(seconds=BOT_STATE_REFRESH_SECONDS):
            return snapshot.allow_proactive_msg

    qq_bot = _pick_qq_bot(bot)
    if qq_bot is None:
        return snapshot.allow_proactive_msg

    try:
        state = await qq_bot.get_group_bot_state(group_id=snapshot.group_openid)
    except Exception as error:
        logger.info(f"获取群 {group_key} 的 bot_state 失败（可能没有白名单权限）：{error!r}")
        async with get_session() as session:
            row = await session.get(BroadcastGroup, group_key)
            if row is not None:
                row.bot_state_checked_at = now
                await session.commit()
        return snapshot.allow_proactive_msg

    async with get_session() as session:
        row = await session.get(BroadcastGroup, group_key)
        if row is not None:
            row.bot_state_checked_at = now
            row.allow_proactive_msg = state.allow_proactive_msg
            row.recv_msg_setting = state.recv_msg_setting
            row.member_role = state.member_role
            row.member_openid = state.member_openid
            row.joined_at = state.joined_at
            await session.commit()
    return state.allow_proactive_msg


async def track_group_event(bot: Bot, event: Event) -> None:
    """收到群消息时更新群列表，并尝试刷新 bot_state"""
    group_qq_number, group_openid = await get_group_ids_from_event(event)
    if not group_qq_number and not group_openid:
        return
    group_key = await record_group_message(group_qq_number, group_openid, datetime.now())
    await refresh_group_bot_state(group_key, bot)

    # 该群如果有等待被动补发的广播，就在这条消息之后安排发送
    if isinstance(event, GroupMessageCreateEvent):
        from .push import schedule_passive_pushes

        await schedule_passive_pushes(group_key, str(event.id), group_openid)


@event_preprocessor
async def _track_group_message(bot: Bot, event: Event) -> None:
    """群列表跟踪不能影响正常消息处理，失败只记日志"""
    try:
        await track_group_event(bot, event)
    except Exception:
        logger.warning(f"更新群列表失败：{traceback.format_exc()}")
