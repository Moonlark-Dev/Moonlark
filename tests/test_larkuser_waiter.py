from typing import ClassVar

import pytest
from unittest.mock import MagicMock, AsyncMock

from fake import fake_group_message_event_v11


def _fake_bot():
    """最小化的 OneBot V11 Bot 替身，供 UniMessage 转换使用"""
    bot = MagicMock()
    bot.adapter.get_name.return_value = "OneBot V11"
    return bot


def _rich_message():
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    return Message(
        [
            MessageSegment.image("https://example.com/a.png"),
            MessageSegment.text("看看这张图"),
        ],
    )


@pytest.fixture
def fake_matcher_factory(monkeypatch):
    """拦截 waiter2 模块的 on_message，避免在测试中注册真实事件响应器"""
    matchers = []

    def factory(*args, **kwargs):
        matchers.append(MagicMock())
        return matchers[-1]

    monkeypatch.setattr("nonebot_plugin_larkuser.utils.waiter2.on_message", factory)
    return matchers


@pytest.fixture
def patched_lang(monkeypatch):
    """替换 LarkUser 共享的 LangHelper 实例方法，隔离数据库访问"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_larkuser.lang import lang

    sent: list[tuple[str, str]] = []
    finished: list[tuple[str, str]] = []

    async def fake_send(key, user_id, *args, **kwargs):
        sent.append((key, str(user_id)))

    async def fake_finish(key, user_id, *args, **kwargs):
        finished.append((key, str(user_id)))
        raise FinishedException

    async def fake_text(key, user_id, *args, **kwargs):
        return f"text::{key}"

    monkeypatch.setattr(lang, "send", fake_send)
    monkeypatch.setattr(lang, "finish", fake_finish)
    monkeypatch.setattr(lang, "text", fake_text)
    return {"sent": sent, "finished": finished}


# ---------------------------------------------------------------- Waiter --


@pytest.mark.asyncio
async def test_waiter_captures_rich_text_message(fake_matcher_factory, patched_lang):
    """Waiter 应捕获包含图片的富文本输入，parser 默认返回 UniMessage 本体"""
    from nonebot_plugin_alconna import Image, Text, UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import Waiter

    received = []

    def checker(message: UniMessage) -> bool:
        received.append(message)
        return True

    waiter = Waiter(prompt_text=UniMessage("请发送内容"), user_id="10", checker=checker)
    event = fake_group_message_event_v11(message=_rich_message())
    matcher = MagicMock()
    matcher.send = AsyncMock()
    await waiter.handle_message(matcher, event, _fake_bot(), "10")

    assert len(received) == 1
    answer = waiter.answer
    assert isinstance(answer, UniMessage)
    assert any(isinstance(seg, Image) for seg in answer)
    assert any(isinstance(seg, Text) and seg.text == "看看这张图" for seg in answer)
    assert waiter.get() is answer


@pytest.mark.asyncio
async def test_waiter_rejects_invalid_input(fake_matcher_factory, patched_lang):
    """checker 不通过时不记录答案，并回复未知输入提示"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import Waiter

    waiter = Waiter(prompt_text=UniMessage("请发送内容"), user_id="10", checker=lambda _: False)
    event = fake_group_message_event_v11(message=_rich_message())
    matcher = MagicMock()
    matcher.send = AsyncMock()
    await waiter.handle_message(matcher, event, _fake_bot(), "10")

    assert waiter.answer is None
    assert patched_lang["sent"] == [("prompt.unknown", "10")]
    with pytest.raises(ValueError):
        waiter.get()


@pytest.mark.asyncio
async def test_waiter_checker_exception_treated_as_invalid(fake_matcher_factory, patched_lang):
    """checker 抛出异常时应视为无效输入而不是崩溃"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import Waiter

    def broken_checker(_: UniMessage) -> bool:
        raise RuntimeError("boom")

    waiter = Waiter(prompt_text=UniMessage("请发送内容"), user_id="10", checker=broken_checker)
    event = fake_group_message_event_v11(message=_rich_message())
    matcher = MagicMock()
    matcher.send = AsyncMock()
    await waiter.handle_message(matcher, event, _fake_bot(), "10")

    assert waiter.answer is None
    assert patched_lang["sent"] == [("prompt.unknown", "10")]


@pytest.mark.asyncio
async def test_waiter_registers_message_matcher(fake_matcher_factory, patched_lang):
    """构造时应注册一个阻断式消息响应器，并挂载处理函数"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import Waiter

    waiter = Waiter(prompt_text=UniMessage("请发送内容"), user_id="10")

    assert len(fake_matcher_factory) == 1
    matcher = fake_matcher_factory[0]
    matcher.handle.assert_called_once()
    matcher.handle.return_value.assert_called_once_with(waiter.handle_message)


@pytest.mark.asyncio
async def test_waiter_wait_timeout_raises_and_destroys_matcher(fake_matcher_factory, patched_lang):
    """超时且无默认值时抛出 TimeoutError，同时销毁响应器避免泄漏"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import Waiter

    waiter = Waiter(prompt_text=UniMessage("请发送内容"), user_id="10")
    stub_prompt = MagicMock()
    stub_prompt.send = AsyncMock()
    waiter.prompt_text = stub_prompt

    with pytest.raises(TimeoutError):
        await waiter.wait(timeout=0, auto_finish=False)

    stub_prompt.send.assert_awaited_once()
    waiter.message_matcher.destroy.assert_called_once()


@pytest.mark.asyncio
async def test_waiter_wait_returns_default_on_timeout(fake_matcher_factory, patched_lang):
    """配置默认值时超时会以默认值结束等待"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import Waiter

    waiter = Waiter(prompt_text=UniMessage("请发送内容"), user_id="10", default=UniMessage("fallback"))
    stub_prompt = MagicMock()
    stub_prompt.send = AsyncMock()
    waiter.prompt_text = stub_prompt

    await waiter.wait(timeout=0, auto_finish=False)

    assert waiter.get().extract_plain_text() == "fallback"
    waiter.message_matcher.destroy.assert_called_once()


# --------------------------------------------------------- WaitUserInput --


@pytest.mark.asyncio
async def test_user_input_checker_receives_plain_text(fake_matcher_factory, patched_lang):
    """WaitUserInput 的 str checker 应收到纯文本而非 UniMessage"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput

    seen = []
    waiter = WaitUserInput(UniMessage("请发送内容"), "10", lambda text: seen.append(text) or True)
    event = fake_group_message_event_v11(message=_rich_message())
    await waiter.handle_message(MagicMock(), event, _fake_bot(), "10")

    assert seen == ["看看这张图"]
    assert waiter.get() == "看看这张图"


@pytest.mark.asyncio
async def test_user_input_parser_over_plain_text(fake_matcher_factory, patched_lang):
    """WaitUserInput 的 parser 输入应保持为纯文本字符串"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput

    waiter = WaitUserInput(UniMessage("请发送内容"), "10")
    event = fake_group_message_event_v11(message=_rich_message())
    await waiter.handle_message(MagicMock(), event, _fake_bot(), "10")

    assert waiter.get(lambda text: text.upper()) == "看看这张图".upper()


@pytest.mark.asyncio
async def test_user_input_default_stays_plain_text(fake_matcher_factory, patched_lang):
    """WaitUserInput 的默认值应以纯文本形式返回"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput

    waiter = WaitUserInput(UniMessage("请发送内容"), "10", default="dd")
    stub_prompt = MagicMock()
    stub_prompt.send = AsyncMock()
    waiter.prompt_text = stub_prompt

    await waiter.wait(timeout=0, auto_finish=False)

    assert waiter.get() == "dd"


@pytest.mark.asyncio
async def test_user_input_rejects_invalid_plain_text(fake_matcher_factory, patched_lang):
    """纯文本检查不通过时同样回复未知输入并保持等待"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput

    waiter = WaitUserInput(UniMessage("请发送内容"), "10", lambda _: False)
    event = fake_group_message_event_v11(message=_rich_message())
    await waiter.handle_message(MagicMock(), event, _fake_bot(), "10")

    assert waiter.answer is None
    assert patched_lang["sent"] == [("prompt.unknown", "10")]


# ---------------------------------------------------------------- prompt --


def _make_fake_waiter_class(script: list):
    class FakeWaitUserInput:
        created: ClassVar[list] = []

        def __init__(self, prompt_text, user_id, **kwargs) -> None:
            self.prompt_text = prompt_text
            self.user_id = user_id
            self.kwargs = kwargs
            FakeWaitUserInput.created.append(self)

        async def wait(self, timeout: int = 210, auto_finish: bool = True) -> None:
            self.timeout = timeout
            self.auto_finish = auto_finish
            if not script:
                raise TimeoutError
            self._answer = script.pop(0)

        def get(self, parser=lambda message: message):
            return parser(self._answer)

    return FakeWaitUserInput


@pytest.mark.asyncio
async def test_prompt_success_applies_parser(monkeypatch, fake_matcher_factory, patched_lang):
    from nonebot_plugin_alconna import UniMessage
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class(["hello"])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    result = await waiter_module.prompt("说点什么", "u1", parser=lambda text: text.upper())

    assert result == "HELLO"
    assert len(fake_cls.created) == 1
    instance = fake_cls.created[0]
    assert isinstance(instance.prompt_text, UniMessage)
    assert instance.user_id == "u1"
    assert instance.timeout == 5 * 60
    assert instance.auto_finish is False


@pytest.mark.asyncio
async def test_prompt_keeps_uni_message_instance(monkeypatch, fake_matcher_factory, patched_lang):
    from nonebot_plugin_alconna import UniMessage
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class(["ok"])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)
    message = UniMessage("原始消息")

    await waiter_module.prompt(message, "u1")

    assert fake_cls.created[0].prompt_text is message


@pytest.mark.asyncio
async def test_prompt_quits_with_q(monkeypatch, fake_matcher_factory, patched_lang):
    from nonebot.exception import FinishedException
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class(["q"])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    with pytest.raises(FinishedException):
        await waiter_module.prompt("说点什么", "u1")

    assert patched_lang["finished"] == [("prompt.quited", "u1")]


@pytest.mark.asyncio
async def test_prompt_q_disabled_passes_to_checker(monkeypatch, fake_matcher_factory, patched_lang):
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class(["q"])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    result = await waiter_module.prompt("说点什么", "u1", checker=lambda text: text == "q", allow_quit=False)

    assert result == "q"


@pytest.mark.asyncio
async def test_prompt_invalid_input_reprompts_with_unknown(monkeypatch, fake_matcher_factory, patched_lang):
    from nonebot_plugin_alconna import UniMessage
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class(["bad", "good"])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    result = await waiter_module.prompt("说点什么", "u1", checker=lambda text: text == "good")

    assert result == "good"
    assert len(fake_cls.created) == 2
    assert isinstance(fake_cls.created[1].prompt_text, UniMessage)
    assert fake_cls.created[1].prompt_text.extract_plain_text() == "text::prompt.unknown"


@pytest.mark.asyncio
async def test_prompt_retry_limit_finishes(monkeypatch, fake_matcher_factory, patched_lang):
    from nonebot.exception import FinishedException
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class(["bad", "bad"])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    with pytest.raises(FinishedException):
        await waiter_module.prompt("说点什么", "u1", checker=lambda _: False, retry=2)

    assert patched_lang["finished"] == [("prompt.retry_too_much", "u1")]
    assert len(fake_cls.created) == 2


@pytest.mark.asyncio
async def test_prompt_retry_too_much_raises_directly(monkeypatch, fake_matcher_factory, patched_lang):
    import nonebot_plugin_larkuser.utils.waiter as waiter_module
    from nonebot_plugin_larkuser.exceptions import PromptRetryTooMuch

    fake_cls = _make_fake_waiter_class([])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    with pytest.raises(PromptRetryTooMuch):
        await waiter_module.prompt("说点什么", "u1", retry=0, ignore_error_details=False)

    assert fake_cls.created == []


@pytest.mark.asyncio
async def test_prompt_timeout_raises_prompt_timeout(monkeypatch, fake_matcher_factory, patched_lang):
    import nonebot_plugin_larkuser.utils.waiter as waiter_module
    from nonebot_plugin_larkuser.exceptions import PromptTimeout

    fake_cls = _make_fake_waiter_class([])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    with pytest.raises(PromptTimeout):
        await waiter_module.prompt("说点什么", "u1", timeout=60, ignore_error_details=False)


@pytest.mark.asyncio
async def test_prompt_timeout_finishes_by_default(monkeypatch, fake_matcher_factory, patched_lang):
    from nonebot.exception import FinishedException
    import nonebot_plugin_larkuser.utils.waiter as waiter_module

    fake_cls = _make_fake_waiter_class([])
    monkeypatch.setattr(waiter_module, "WaitUserInput", fake_cls)

    with pytest.raises(FinishedException):
        await waiter_module.prompt("说点什么", "u1", timeout=60)

    assert patched_lang["finished"] == [("prompt.timeout", "u1")]
