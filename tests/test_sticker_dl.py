from typing import ClassVar

import pytest


class _FakeWaiter:
    """替换 nonebot_plugin_sticker_dl.__main__.Waiter 的测试替身"""

    created: ClassVar[list] = []
    responses: ClassVar[list] = []
    sent: ClassVar[list] = []

    def __init__(self, prompt_text, user_id, checker=None, default=None, event=None) -> None:
        self.prompt_text = prompt_text
        self.user_id = user_id
        self.event = event
        type(self).created.append(self)

    async def wait(self, timeout: int = 210, auto_finish: bool = True) -> None:
        self.timeout = timeout
        self.auto_finish = auto_finish
        response = type(self).responses.pop(0)
        if isinstance(response, Exception):
            raise response
        self._message = response

    def get(self, parser=lambda message: message):
        return parser(self._message)

    def get_event(self):
        return self.event

    async def send_message(self, message) -> None:
        type(self).sent.append(message)

    async def finish(self, key: str, user_id=None):
        from nonebot.exception import FinishedException

        type(self).sent.append(("finish", key))
        raise FinishedException


@pytest.fixture
def sticker_dl_env(monkeypatch):
    """隔离 __main__ 模块的外部依赖：Waiter、image_fetch 与 lang"""
    import nonebot_plugin_sticker_dl.__main__ as mod

    fetched: list = []

    async def fake_image_fetch(event, bot, state, image, **kwargs):
        fetched.append(image)
        return b"raw-image"

    async def fake_lang_text(key: str, user_id, *args, **kwargs) -> str:
        return f"text::{key}"

    monkeypatch.setattr(mod, "Waiter", _FakeWaiter)
    monkeypatch.setattr(mod, "image_fetch", fake_image_fetch)
    monkeypatch.setattr(mod.lang, "text", fake_lang_text)

    _FakeWaiter.created.clear()
    _FakeWaiter.responses.clear()
    _FakeWaiter.sent.clear()
    fetched.clear()
    mod.active_users.clear()
    return {"fetched": fetched, "mod": mod}


@pytest.mark.asyncio
async def test_image_echoed_then_non_image_quits(sticker_dl_env):
    """收到图片消息时原样发回，收到非图片消息后退出模式"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Image, Text, UniMessage
    from nonebot_plugin_sticker_dl.__main__ import run_downloader

    _FakeWaiter.responses.append(UniMessage([Image(url="https://example.com/a.png")]))
    _FakeWaiter.responses.append(UniMessage([Text("不发了")]))

    with pytest.raises(FinishedException):
        await run_downloader(None, {}, "user-1")

    assert len(_FakeWaiter.created) == 2
    assert _FakeWaiter.created[0].timeout == 5 * 60
    assert _FakeWaiter.created[0].auto_finish is False

    # 第一次等待后把下载到的图片发回
    assert len(_FakeWaiter.sent) == 2
    echoed = _FakeWaiter.sent[0]
    assert len(echoed) == 1
    assert isinstance(echoed[0], Image)
    assert echoed[0].raw == b"raw-image"
    # 收到非图片消息后退出
    assert _FakeWaiter.sent[1] == ("finish", "quit")


@pytest.mark.asyncio
async def test_non_image_quits_immediately(sticker_dl_env):
    """第一条消息不是图片时直接退出，不发送任何图片"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_sticker_dl.__main__ import run_downloader

    _FakeWaiter.responses.append(UniMessage([Text("hello")]))

    with pytest.raises(FinishedException):
        await run_downloader(None, {}, "user-1")

    assert _FakeWaiter.sent == [("finish", "quit")]
    assert sticker_dl_env["fetched"] == []


@pytest.mark.asyncio
async def test_timeout_exits_mode(sticker_dl_env):
    """等待超时时退出模式"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_sticker_dl.__main__ import run_downloader

    _FakeWaiter.responses.append(TimeoutError())

    with pytest.raises(FinishedException):
        await run_downloader(None, {}, "user-1")

    assert _FakeWaiter.sent == [("finish", "timeout")]


@pytest.mark.asyncio
async def test_download_failure_forwards_original_segment(sticker_dl_env):
    """下载失败时回退为直接转发原始图片消息段"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Image, Text, UniMessage
    from nonebot_plugin_sticker_dl.__main__ import run_downloader

    async def failing_image_fetch(event, bot, state, image, **kwargs):
        return None

    sticker_dl_env["mod"].image_fetch = failing_image_fetch
    _FakeWaiter.responses.append(UniMessage([Image(url="https://example.com/a.png")]))
    _FakeWaiter.responses.append(UniMessage([Text("退出")]))

    with pytest.raises(FinishedException):
        await run_downloader(None, {}, "user-1")

    echoed = _FakeWaiter.sent[0]
    assert isinstance(echoed[0], Image)
    assert echoed[0].url == "https://example.com/a.png"


def test_rule_rejects_reentry(sticker_dl_env):
    """已在模式中的用户重新发送指令时，指令响应器不再匹配"""
    mod = sticker_dl_env["mod"]

    assert mod.is_not_downloading("user-1") is True
    mod.active_users.add("user-1")
    assert mod.is_not_downloading("user-1") is False
    assert mod.is_not_downloading("user-2") is True


@pytest.mark.asyncio
async def test_handler_enters_and_cleans_up(sticker_dl_env):
    """正常进入模式，退出后清理模式登记"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Text, UniMessage

    mod = sticker_dl_env["mod"]
    _FakeWaiter.responses.append(UniMessage([Text("hello")]))

    with pytest.raises(FinishedException):
        await mod.handle_sticker_dl(None, {}, user_id="user-2")

    assert _FakeWaiter.sent[-1] == ("finish", "quit")
    assert mod.active_users == set()
