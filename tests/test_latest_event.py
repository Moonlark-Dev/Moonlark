from typing import ClassVar

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_latest_event_updates_and_sends_to_newest(monkeypatch):
    """LatestEvent 应忽略空更新，并把消息发送到最新事件。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkutils import LatestEvent

    send = AsyncMock()
    monkeypatch.setattr(UniMessage, "send", send)

    bot = MagicMock()
    first = MagicMock()
    second = MagicMock()
    tracker = LatestEvent(first, bot)
    tracker.update(None)
    assert tracker.event is first
    tracker.update(second)

    await tracker.send("hello", at_sender=True)

    send.assert_awaited_once()
    assert send.await_args.kwargs["target"] is second
    assert send.await_args.kwargs["bot"] is bot
    assert send.await_args.kwargs["at_sender"] is True


class _FakeWaiter:
    """替换 ftt AnswerGetter 使用的 Waiter，记录提示目标并回传新事件。"""

    created: ClassVar[list] = []
    responses: ClassVar[list] = []
    events: ClassVar[list] = []

    def __init__(self, prompt_text, user_id, checker=None, default=None, event=None, rule=None) -> None:
        self.prompt_text = prompt_text
        self.event = event
        type(self).created.append(self)

    async def wait(self, timeout: int = 210, auto_finish: bool = True) -> None:
        self.timeout = timeout
        self.auto_finish = auto_finish

    def get_event(self):
        return type(self).events.pop(0)

    def get(self, parser=lambda message: message):
        return parser(type(self).responses.pop(0))


@pytest.fixture
def ftt_env(monkeypatch):
    import nonebot_plugin_finding_the_trail.utils.answer as mod

    monkeypatch.setattr(mod, "Waiter", _FakeWaiter)
    _FakeWaiter.created.clear()
    _FakeWaiter.responses.clear()
    _FakeWaiter.events.clear()
    return mod


@pytest.mark.asyncio
async def test_ftt_answer_getter_targets_latest_event(ftt_env):
    """每轮输入后应更新 tracker，使下一次提示回复到最新消息。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkutils import LatestEvent

    first = object()
    second = object()
    tracker = LatestEvent(first)
    getter = ftt_env.AnswerGetter("user", MagicMock(), tracker)

    _FakeWaiter.responses.append(UniMessage("wsd"))
    _FakeWaiter.events.append(second)

    directions = await getter.get_input()

    assert [direction.value for direction in directions] == [1, 2, 4]
    assert _FakeWaiter.created[0].event is first
    assert tracker.event is second
