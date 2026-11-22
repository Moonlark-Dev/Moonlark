"""bots 事件预处理器应忽略 OneBot 心跳元事件

心跳等元事件不携带用户与会话上下文，若交给 bots 的路由逻辑处理，会把空会话
写进 sessions 并刷出「已将会话  分配给 …」的日志（线上约每 5 秒一次）。
"""

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fake import fake_group_message_event_v11


def _heartbeat_event_v11():
    from nonebot.adapters.onebot.v11.event import HeartbeatMetaEvent, Status

    return HeartbeatMetaEvent(
        time=int(time.time()),
        self_id=1,
        post_type="meta_event",
        meta_event_type="heartbeat",
        interval=5000,
        status=Status(online=True, good=True),
    )


def _heartbeat_event_v12():
    from nonebot.adapters.onebot.v12.event import HeartbeatMetaEvent

    return HeartbeatMetaEvent(
        id="pytest",
        time=datetime.fromtimestamp(time.time(), tz=timezone.utc),
        type="meta",
        detail_type="heartbeat",
        sub_type="",
        interval=5000,
    )


async def test_heartbeat_meta_events_are_ignored() -> None:
    """V11 / V12 心跳不应进入绑定检测与会话分配"""
    from nonebot_plugin_bots import __main__ as bots_main

    bot = SimpleNamespace(self_id="1")
    sessions_before = dict(bots_main.sessions)
    with patch.object(
        bots_main,
        "_get_bound_group",
        AsyncMock(side_effect=AssertionError("心跳事件不应进入会话处理")),
    ):
        await bots_main.preprocess_event(bot, _heartbeat_event_v11(), "")
        await bots_main.preprocess_event(bot, _heartbeat_event_v12(), "")

    assert bots_main.sessions == sessions_before
    assert "" not in bots_main.sessions


async def test_group_message_still_assigned_to_session() -> None:
    """普通群消息仍然按原有逻辑分配会话，避免跳过心跳时误伤正常事件"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_bots import __main__ as bots_main

    bots_main.sessions.pop("qq_20002", None)
    event = fake_group_message_event_v11(user_id=10001, group_id=20002, original_message=Message("test"))
    bot = SimpleNamespace(self_id="10002")
    with (
        patch.object(bots_main, "try_process_bind_code", AsyncMock(return_value=False)),
        patch.object(bots_main, "_get_bound_group", AsyncMock(return_value=None)),
    ):
        await bots_main.preprocess_event(bot, event, "qq_20002")

    assert bots_main.sessions["qq_20002"][0] == "10002"
