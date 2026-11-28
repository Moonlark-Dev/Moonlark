"""广播推送事件与被动补发

QQ 官方机器人的主动消息推送受白名单/配额限制（``bot_state`` 里的
``allow_proactive_msg``）。没有开启主动推送的群聊不能立即推送，于是在该群
收到下一条消息后延迟三分钟，用那条消息的 id 走被动消息回复。

每次广播、每个群的推送尝试都会写进 ``BroadcastPushEvent`` 表；广播本身写在
``BroadcastRecord``，并维护 queued/running/done/failed 状态，供 HTTP 接口查询进度。
"""

import asyncio
import json
import secrets
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from nonebot import get_bots
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot.log import logger
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_orm import get_session
from sqlalchemy import func, or_, select

from .groups import get_group_snapshot, refresh_group_bot_state, resolve_group_key
from .message import BroadcastButton, build_broadcast_message, build_qq_broadcast_message, render_broadcast_image
from .models import (
    BROADCAST_ACTIVE_STATUSES,
    BROADCAST_STATUS_DONE,
    BROADCAST_STATUS_FAILED,
    BROADCAST_STATUS_QUEUED,
    BROADCAST_STATUS_RUNNING,
    BroadcastPushEvent,
    BroadcastRecord,
)

# 被动补发延迟：收到下一条群消息后等待的秒数（QQ 被动消息的有效期是 5 分钟）
PASSIVE_PUSH_DELAY_SECONDS = 180

# 群发间隔，避免同一时间向大量群聊发送
SEND_INTERVAL_RANGE = (1, 7)

# 处于 queued/running 超过该时长的记录视为进程中断留下的僵尸，
# 不再阻塞新的广播（需要在下次查询时自动标为 failed）。
INFLIGHT_STALE_SECONDS = 3600

# 已调度的被动补发任务：推送事件 id -> task，避免同一事件被重复调度
_passive_tasks: dict[int, asyncio.Task] = {}


@dataclass
class BroadcastPushResult:
    """一次广播的最终统计"""

    broadcast_id: int
    total: int = 0
    sent: int = 0
    pending: int = 0
    failed: int = 0


@dataclass
class BroadcastRecordSnapshot:
    """脱离 ORM Session 后仍可安全读取的广播记录快照"""

    id: int
    content: str
    buttons: list[BroadcastButton] = field(default_factory=list)
    submitter: Optional[str] = None
    request_id: Optional[str] = None
    request_hash: Optional[str] = None
    status: str = BROADCAST_STATUS_DONE
    total: int = 0
    created_at: Optional[datetime] = None


@dataclass
class BroadcastEventSnapshot:
    """单条推送事件快照"""

    id: int
    group_key: str
    group_openid: Optional[str]
    bot_id: str
    adapter: str
    mode: str
    status: str
    error: Optional[str]
    passive_msg_id: Optional[str]
    created_at: Optional[datetime]
    sent_at: Optional[datetime]


def _parse_buttons(raw: Optional[str]) -> list[BroadcastButton]:
    try:
        parsed = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        BroadcastButton(label=str(item.get("label", "")), text=str(item.get("text", "")))
        for item in parsed
        if isinstance(item, dict)
    ]


def _record_snapshot(row: BroadcastRecord) -> BroadcastRecordSnapshot:
    return BroadcastRecordSnapshot(
        id=row.id,
        content=row.content,
        buttons=_parse_buttons(row.buttons),
        submitter=row.submitter,
        request_id=row.request_id,
        request_hash=row.request_hash,
        status=row.status,
        total=row.total,
        created_at=row.created_at,
    )


def _event_snapshot(row: BroadcastPushEvent) -> BroadcastEventSnapshot:
    return BroadcastEventSnapshot(
        id=row.id,
        group_key=row.group_key,
        group_openid=row.group_openid,
        bot_id=row.bot_id,
        adapter=row.adapter,
        mode=row.mode,
        status=row.status,
        error=row.error,
        passive_msg_id=row.passive_msg_id,
        created_at=row.created_at,
        sent_at=row.sent_at,
    )


async def create_broadcast_record(
    content: str,
    buttons: list[BroadcastButton],
    submitter: Optional[str] = None,
    *,
    request_id: Optional[str] = None,
    request_hash: Optional[str] = None,
    total: int = 0,
    status: str = BROADCAST_STATUS_DONE,
) -> int:
    """保存本次广播的内容快照，返回广播 id"""
    async with get_session() as session:
        record = BroadcastRecord(
            content=content,
            buttons=json.dumps(buttons, ensure_ascii=False),
            submitter=submitter,
            request_id=request_id,
            request_hash=request_hash,
            total=total,
            status=status,
            # 显式写入 Python 本地时间：created_at 的 server_default 在 SQLite 是 UTC、
            # 在 MySQL 是数据库会话时区，和后面用 datetime.now() 判断僵尸记录的口径不一致
            created_at=datetime.now(),
        )
        session.add(record)
        await session.flush()
        broadcast_id = record.id
        await session.commit()
    return broadcast_id


async def get_broadcast_record(broadcast_id: int) -> Optional[BroadcastRecordSnapshot]:
    """按 id 读取广播记录，不存在时返回 None"""
    async with get_session() as session:
        row = await session.get(BroadcastRecord, broadcast_id)
        return _record_snapshot(row) if row is not None else None


async def get_broadcast_by_request_id(request_id: str) -> Optional[BroadcastRecordSnapshot]:
    """按 HTTP 幂等键读取广播记录"""
    async with get_session() as session:
        row = await session.scalar(select(BroadcastRecord).where(BroadcastRecord.request_id == request_id))
        return _record_snapshot(row) if row is not None else None


async def find_inflight_broadcast() -> Optional[BroadcastRecordSnapshot]:
    """找出仍在 queued/running 的广播

    超过 ``INFLIGHT_STALE_SECONDS`` 的记录视为进程异常退出留下的僵尸，顺手标为
    failed，否则一次崩溃就会让 HTTP 接口永远无法再发起广播。
    """
    stale_before = datetime.now() - timedelta(seconds=INFLIGHT_STALE_SECONDS)
    async with get_session() as session:
        stale = (
            await session.scalars(
                select(BroadcastRecord).where(
                    BroadcastRecord.status.in_(BROADCAST_ACTIVE_STATUSES),
                    BroadcastRecord.created_at < stale_before,
                )
            )
        ).all()
        for row in stale:
            row.status = BROADCAST_STATUS_FAILED
        if stale:
            logger.warning(f"清理 {len(stale)} 条超时未结束的广播记录")
            await session.commit()
        row = await session.scalar(
            select(BroadcastRecord)
            .where(BroadcastRecord.status.in_(BROADCAST_ACTIVE_STATUSES))
            .order_by(BroadcastRecord.id.desc())
            .limit(1)
        )
        return _record_snapshot(row) if row is not None else None


async def get_broadcast_stats(broadcast_id: int) -> dict[str, int]:
    """按状态统计一次广播的推送事件（sent/pending/failed）"""
    stats = {"sent": 0, "pending": 0, "failed": 0}
    async with get_session() as session:
        rows = (
            await session.execute(
                select(BroadcastPushEvent.status, func.count())
                .where(BroadcastPushEvent.broadcast_id == broadcast_id)
                .group_by(BroadcastPushEvent.status)
            )
        ).all()
    for status_value, count in rows:
        stats[status_value] = count
    return stats


async def list_broadcast_events(broadcast_id: int, limit: int = 500) -> list[BroadcastEventSnapshot]:
    """列出一次广播的逐群推送事件（最多 ``limit`` 条）"""
    async with get_session() as session:
        rows = (
            await session.scalars(
                select(BroadcastPushEvent)
                .where(BroadcastPushEvent.broadcast_id == broadcast_id)
                .order_by(BroadcastPushEvent.id.asc())
                .limit(limit)
            )
        ).all()
    return [_event_snapshot(row) for row in rows]


async def _set_record_status(broadcast_id: int, status: str) -> None:
    async with get_session() as session:
        record = await session.get(BroadcastRecord, broadcast_id)
        if record is not None:
            record.status = status
            await session.commit()


async def record_push_event(
    broadcast_id: int,
    group_key: str,
    group_openid: Optional[str],
    bot: Bot,
    mode: str,
    status: str,
    error: Optional[str] = None,
    passive_msg_id: Optional[str] = None,
) -> int:
    """记录一次推送事件"""
    async with get_session() as session:
        event = BroadcastPushEvent(
            broadcast_id=broadcast_id,
            group_key=group_key,
            group_openid=group_openid,
            bot_id=str(bot.self_id),
            adapter=bot.adapter.get_name(),
            mode=mode,
            status=status,
            error=error,
            passive_msg_id=passive_msg_id,
            sent_at=datetime.now() if status == "sent" else None,
        )
        session.add(event)
        await session.flush()
        event_id = event.id
        await session.commit()
    return event_id


async def send_qq_group_message(
    message: UniMessage,
    bot: QQBot,
    group_openid: str,
    source: str = "",
    reply_seq: Optional[int] = None,
) -> None:
    """发送 QQ 官方群消息

    ``source`` 为空时是主动消息；给出消息 id 时适配器会按被动消息回复。
    """
    target = Target(group_openid, source=source, adapter=bot.adapter.get_name(), self_id=bot.self_id)
    if reply_seq is not None:
        target.extra["qq.reply_seq"] = reply_seq
    await message.send(target=target, bot=bot)


async def run_broadcast(
    broadcast_id: int,
    groups: dict[str, list[Bot]],
    content: str,
    buttons: list[BroadcastButton],
) -> BroadcastPushResult:
    """把一次已登记的广播发送到 ``groups``，并维护记录状态

    ``groups`` 的键是实际发送时使用的群标识（OneBot 群号或 QQ ``group_openid``），
    每个群只推一次。HTTP 接口在后台任务里调用它，CLI 的 ``bcsu submit`` 则同步调用。
    """
    result = BroadcastPushResult(broadcast_id=broadcast_id, total=len(groups))
    await _set_record_status(broadcast_id, BROADCAST_STATUS_RUNNING)
    image: Optional[bytes] = None

    try:
        for group_id, bots in groups.items():
            for bot in bots:
                if isinstance(bot, QQBot):
                    group_key = await resolve_group_key(group_id)
                    snapshot = await get_group_snapshot(group_key)
                    openid = snapshot.group_openid if snapshot else None
                    openid = openid or group_id
                    # 主动消息是否可用取决于 bot_state；查询失败/没有白名单时视为不可用
                    allow_proactive = await refresh_group_bot_state(group_key, bot)
                    if allow_proactive is not True:
                        await record_push_event(broadcast_id, group_key, openid, bot, "passive", "pending")
                        result.pending += 1
                        break
                    try:
                        await send_qq_group_message(build_qq_broadcast_message(content, buttons), bot, openid)
                    except Exception:
                        error = traceback.format_exc()
                        logger.warning(f"使用 {bot.self_id} 在 {group_id} 主动推送广播失败：{error}")
                        await record_push_event(
                            broadcast_id, group_key, openid, bot, "active", "failed", error=error[-2000:]
                        )
                        result.failed += 1
                    else:
                        await record_push_event(broadcast_id, group_key, openid, bot, "active", "sent")
                        result.sent += 1
                    break

                try:
                    if image is None:
                        image = await render_broadcast_image(content)
                    message = await build_broadcast_message(bot, content, buttons, image)
                    target = Target(group_id, self_id=bot.self_id, adapter=bot.adapter.get_name())
                    await message.send(target=target, bot=bot)
                except Exception:
                    error = traceback.format_exc()
                    logger.warning(f"使用 {bot.self_id} 在 {group_id} 推送失败：{error}")
                    await record_push_event(broadcast_id, group_id, None, bot, "active", "failed", error=error[-2000:])
                    result.failed += 1
                else:
                    await record_push_event(broadcast_id, group_id, None, bot, "active", "sent")
                    result.sent += 1
                break

            low, high = SEND_INTERVAL_RANGE
            # 随机间隔，避免同一时间向大量群聊连发（与安全无关，用 secrets 避开静态检查误报）
            await asyncio.sleep(low + secrets.randbelow(high - low + 1))
    except asyncio.CancelledError:
        await _set_record_status(broadcast_id, BROADCAST_STATUS_FAILED)
        raise
    except Exception:
        await _set_record_status(broadcast_id, BROADCAST_STATUS_FAILED)
        logger.exception(f"广播 #{broadcast_id} 发送流程异常中断")
        raise

    await _set_record_status(broadcast_id, BROADCAST_STATUS_DONE)
    return result


async def push_broadcast(
    groups: dict[str, list[Bot]],
    content: str,
    buttons: list[BroadcastButton],
    submitter: Optional[str] = None,
) -> tuple[int, int]:
    """记录并推送一次广播

    Returns:
        ``(立即推送成功数, 转入被动补发数)``
    """
    result = await push_broadcast_detailed(groups, content, buttons, submitter)
    return result.sent, result.pending


async def push_broadcast_detailed(
    groups: dict[str, list[Bot]],
    content: str,
    buttons: list[BroadcastButton],
    submitter: Optional[str] = None,
) -> BroadcastPushResult:
    """与 :func:`push_broadcast` 相同，但返回完整统计（含失败数）"""
    broadcast_id = await create_broadcast_record(
        content,
        buttons,
        submitter,
        total=len(groups),
        status=BROADCAST_STATUS_RUNNING,
    )
    return await run_broadcast(broadcast_id, groups, content, buttons)


async def schedule_passive_pushes(group_key: str, message_id: str, group_openid: Optional[str] = None) -> None:
    """收到群消息后，调度该群里所有等待补发的广播

    同一个推送事件只会被调度一次：三分钟的等待期内再收到消息也不会重新计时，
    否则消息越活跃的群聊反而永远等不到补发。
    """
    condition = BroadcastPushEvent.group_key == group_key
    if group_openid:
        # 广播提交后才完成 GroupBind 时，事件仍记在 openid 键下
        condition = or_(condition, BroadcastPushEvent.group_openid == group_openid)
    async with get_session() as session:
        events = (
            await session.scalars(
                select(BroadcastPushEvent).where(
                    condition,
                    BroadcastPushEvent.mode == "passive",
                    BroadcastPushEvent.status == "pending",
                )
            )
        ).all()
        pending = [(event.id, event.group_openid) for event in events]

    for index, (event_id, group_openid) in enumerate(pending):
        if event_id in _passive_tasks:
            continue
        # 同一条消息最多被动回复 5 次，msg_seq 需要区分开
        task = asyncio.create_task(
            deliver_passive_push(event_id, group_openid, message_id, reply_seq=index % 5),
        )
        _passive_tasks[event_id] = task
        task.add_done_callback(lambda _task, eid=event_id: _passive_tasks.pop(eid, None))


async def deliver_passive_push(
    event_id: int,
    group_openid: Optional[str],
    message_id: str,
    reply_seq: int = 0,
) -> None:
    """延迟三分钟后用被动消息补发一条广播"""
    await asyncio.sleep(PASSIVE_PUSH_DELAY_SECONDS)

    async with get_session() as session:
        event = await session.get(BroadcastPushEvent, event_id)
        if event is None or event.status != "pending":
            return
        record = await session.get(BroadcastRecord, event.broadcast_id)
        if record is None:
            event.status = "failed"
            event.error = "广播内容记录不存在"
            await session.commit()
            return
        bot_id = event.bot_id
        openid = event.group_openid or group_openid
        content = record.content
        buttons = json.loads(record.buttons or "[]")

    bot = get_bots().get(bot_id)
    if not isinstance(bot, QQBot) or not openid:
        # bot 不在线时保留 pending，等该群下一条消息再补发
        logger.info(f"广播 {event_id} 被动补发暂缓：bot {bot_id} 不在线或缺少群 openid")
        return

    try:
        await send_qq_group_message(
            build_qq_broadcast_message(content, buttons),
            bot,
            openid,
            source=message_id,
            reply_seq=reply_seq,
        )
    except Exception:
        error = traceback.format_exc()
        logger.warning(f"广播 {event_id} 被动补发失败：{error}")
        async with get_session() as session:
            event = await session.get(BroadcastPushEvent, event_id)
            if event is not None:
                event.status = "failed"
                event.error = error[-2000:]
                event.passive_msg_id = message_id
                await session.commit()
        return

    async with get_session() as session:
        event = await session.get(BroadcastPushEvent, event_id)
        if event is not None and event.status == "pending":
            event.status = "sent"
            event.sent_at = datetime.now()
            event.passive_msg_id = message_id
            await session.commit()
