"""广播推送事件与被动消息补发测试

覆盖：
1. 未开启主动消息推送的 QQ 群只记录 pending 事件，不立即发送；
2. 已开启主动消息推送的群立即以主动消息发送；
3. 收到群消息三分钟后，用该消息的 id 以被动消息补发；
4. 同一事件不会被重复调度。
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select


def _qq_bot(allow_proactive: bool) -> MagicMock:
    from nonebot.adapters.qq import Bot as QQBot

    bot = MagicMock(spec=QQBot)
    bot.self_id = "102"
    bot.adapter = MagicMock()
    bot.adapter.get_name.return_value = "QQ"
    bot.get_group_bot_state = AsyncMock(
        return_value=SimpleNamespace(
            allow_proactive_msg=allow_proactive,
            recv_msg_setting="all",
            member_role="member",
            member_openid="bot-openid",
            joined_at=datetime.now(),
        )
    )
    return bot


async def _record(openid: str) -> None:
    from nonebot_plugin_broadcast.groups import record_group_message

    await record_group_message(None, openid, datetime.now())


async def _get_event(group_key: str):
    from nonebot_plugin_broadcast.models import BroadcastPushEvent
    from nonebot_plugin_orm import get_session

    async with get_session() as session:
        return await session.scalar(select(BroadcastPushEvent).where(BroadcastPushEvent.group_key == group_key))


@pytest.mark.asyncio
async def test_push_defers_when_proactive_message_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import groups, push

    openid = "openid-push-deferred"
    await _record(openid)
    qq_bot = _qq_bot(allow_proactive=False)
    monkeypatch.setattr(groups, "_pick_qq_bot", lambda bot=None: qq_bot)
    monkeypatch.setattr(push, "SEND_INTERVAL_RANGE", (0, 0))
    send = AsyncMock()
    monkeypatch.setattr(push, "send_qq_group_message", send)

    sent, pending = await push.push_broadcast({openid: [qq_bot]}, "广播内容", [], submitter="10001")

    assert (sent, pending) == (0, 1)
    send.assert_not_awaited()
    event = await _get_event(openid)
    assert event is not None
    assert event.mode == "passive"
    assert event.status == "pending"
    assert event.group_openid == openid


@pytest.mark.asyncio
async def test_push_sends_active_when_proactive_message_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import groups, push

    openid = "openid-push-active"
    await _record(openid)
    qq_bot = _qq_bot(allow_proactive=True)
    monkeypatch.setattr(groups, "_pick_qq_bot", lambda bot=None: qq_bot)
    monkeypatch.setattr(push, "SEND_INTERVAL_RANGE", (0, 0))
    send = AsyncMock()
    monkeypatch.setattr(push, "send_qq_group_message", send)

    sent, pending = await push.push_broadcast({openid: [qq_bot]}, "广播内容", [], submitter="10001")

    assert (sent, pending) == (1, 0)
    send.assert_awaited_once()
    event = await _get_event(openid)
    assert event is not None
    assert event.mode == "active"
    assert event.status == "sent"
    assert event.sent_at is not None


@pytest.mark.asyncio
async def test_passive_push_uses_message_id_after_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import groups, push

    openid = "openid-push-passive"
    await _record(openid)
    qq_bot = _qq_bot(allow_proactive=False)
    monkeypatch.setattr(groups, "_pick_qq_bot", lambda bot=None: qq_bot)
    monkeypatch.setattr(push, "SEND_INTERVAL_RANGE", (0, 0))
    monkeypatch.setattr(push, "send_qq_group_message", AsyncMock())
    await push.push_broadcast({openid: [qq_bot]}, "广播内容", [], submitter="10001")

    event = await _get_event(openid)
    assert event is not None

    send = AsyncMock()
    monkeypatch.setattr(push, "send_qq_group_message", send)
    monkeypatch.setattr(push, "PASSIVE_PUSH_DELAY_SECONDS", 0)
    monkeypatch.setattr(push, "get_bots", lambda: {"102": qq_bot})

    await push.deliver_passive_push(event.id, openid, "message-id-1")

    send.assert_awaited_once()
    call = send.await_args
    assert call.kwargs["source"] == "message-id-1"
    updated = await _get_event(openid)
    assert updated is not None
    assert updated.status == "sent"
    assert updated.passive_msg_id == "message-id-1"


@pytest.mark.asyncio
async def test_schedule_passive_push_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import groups, push

    openid = "openid-push-schedule"
    await _record(openid)
    qq_bot = _qq_bot(allow_proactive=False)
    monkeypatch.setattr(groups, "_pick_qq_bot", lambda bot=None: qq_bot)
    monkeypatch.setattr(push, "SEND_INTERVAL_RANGE", (0, 0))
    monkeypatch.setattr(push, "send_qq_group_message", AsyncMock())
    await push.push_broadcast({openid: [qq_bot]}, "广播内容", [], submitter="10001")

    # 让补发任务「一直等待」，模拟三分钟的延迟窗口，验证窗口内不会重复调度
    async def _blocking(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(60)

    deliver = AsyncMock(side_effect=_blocking)
    monkeypatch.setattr(push, "deliver_passive_push", deliver)
    await push.schedule_passive_pushes(openid, "message-id-2")
    await push.schedule_passive_pushes(openid, "message-id-3")

    deliver.assert_awaited_once()
    assert deliver.await_args.args[2] == "message-id-2"
    for task in list(push._passive_tasks.values()):
        task.cancel()
    await asyncio.sleep(0)
