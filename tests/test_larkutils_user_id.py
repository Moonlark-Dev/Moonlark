import time
from unittest.mock import AsyncMock, patch

import pytest
from loguru import logger

from fake import fake_group_message_event_v11


def _heartbeat_event():
    """OneBot V11 心跳元事件：不含用户上下文，get_user_id() 会抛 ValueError"""
    from nonebot.adapters.onebot.v11.event import HeartbeatMetaEvent, Status

    return HeartbeatMetaEvent(
        time=int(time.time()),
        self_id=1,
        post_type="meta_event",
        meta_event_type="heartbeat",
        interval=5000,
        status=Status(online=True, good=True),
    )


class _NoUserContextEvent:
    """模拟未实现 get_user_id() 的适配器事件"""

    def __init__(self) -> None:
        self.type = "notice"

    def get_type(self) -> str:
        return self.type

    def get_user_id(self) -> str:
        raise NotImplementedError


@pytest.fixture
def log_records():
    """收集 loguru 日志记录，用于断言不再输出 ERROR"""
    records: list = []
    sink_id = logger.add(lambda message: records.append(message.record), level="TRACE")
    yield records
    logger.remove(sink_id)


@pytest.mark.asyncio
async def test_get_user_id_returns_placeholder_for_meta_event(log_records: list) -> None:
    """心跳等元事件没有用户上下文：返回 -1，且不能按 ERROR 记录（会刷屏）"""
    from nonebot_plugin_larkutils.user import _get_user_id

    with patch("nonebot_plugin_larkutils.user.get_main_account", new=AsyncMock()) as get_main_account:
        assert await _get_user_id(_heartbeat_event()) == "-1"
        # 没有用户 ID 时不应该查数据库
        get_main_account.assert_not_called()

    errors = [
        record
        for record in log_records
        if record["name"].startswith("nonebot_plugin_larkutils") and record["level"].name in {"ERROR", "CRITICAL"}
    ]
    assert errors == []


@pytest.mark.asyncio
async def test_get_user_id_returns_placeholder_for_not_implemented(log_records: list) -> None:
    """适配器未实现 get_user_id() 时同样返回 -1，且不记录 ERROR"""
    from nonebot_plugin_larkutils.user import _get_user_id

    assert await _get_user_id(_NoUserContextEvent()) == "-1"

    errors = [
        record
        for record in log_records
        if record["name"].startswith("nonebot_plugin_larkutils") and record["level"].name in {"ERROR", "CRITICAL"}
    ]
    assert errors == []


@pytest.mark.asyncio
async def test_get_user_id_resolves_main_account() -> None:
    """带用户上下文的消息事件仍然解析主账号"""
    from nonebot_plugin_larkutils.user import _get_user_id

    from nonebot.adapters.onebot.v11 import Message

    event = fake_group_message_event_v11(user_id=10001, original_message=Message("test"))
    with patch(
        "nonebot_plugin_larkutils.user.get_main_account",
        new=AsyncMock(return_value="10001"),
    ) as get_main_account:
        assert await _get_user_id(event) == "10001"
        get_main_account.assert_awaited_once_with("10001")
