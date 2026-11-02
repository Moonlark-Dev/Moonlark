"""nonebot_plugin_email 的 QQ 官方 markdown 展示回归测试。

QQ 官方机器人下，未读邮件列表以 markdown 文本发送：不渲染图片，一键领取/全部已读
改用键盘按钮下发，markdown 里既没有 <qqbot-cmd-input>，也不再展示 claim / read /
查看未读邮件的用法说明；其余平台仍只发送邮件列表渲染图。
"""

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _Finished(Exception):
    """用于截断 matcher.finish 的哨兵异常"""


class _FakeLang:
    def __init__(self, templates: dict[str, str]) -> None:
        self.templates = templates

    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return self.templates.get(key, key).format(*args, __prefix__="/")


_TEMPLATES = {
    "email_list.title": "邮件列表",
    "email_list.title_md": "## 邮件列表（共 {} 封）",
    "email_list.empty": "> 暂无未读邮件。",
    "email_list.time": "时间: {}",
    "email_list.from": "来自: {}",
    "email_list.email_id": "邮件 ID: {}",
    "email_list.subject_md": "### {}",
    "email_list.items": "包含的物品",
    "email_list.claimed": "已领取",
    "email_list.claimed_md": "> 已领取",
    "email_list.item_md": "- {} ×{}",
    "button.claim_all": "一键领取",
    "button.read_all": "全部已读",
}


def _fake_email(subject: str = "测试邮件", content: str = "第一行\n第二行", is_claimed: bool = False) -> dict:
    from nonebot_plugin_email.types import DictEmailData

    data: DictEmailData = {
        "id": 7,
        "author": "Moonlark",
        "content": content,
        "subject": subject,
        "time": datetime.datetime(2026, 10, 14, 8, 30, 0),
        "items": [{"item_id": "moonlark:egg", "count": 3, "data": {}}],
        "is_read": False,
        "is_claimed": is_claimed,
    }
    return data


@pytest.fixture
def email_env(monkeypatch: pytest.MonkeyPatch):
    """打桩邮件数据与本地化"""
    import nonebot_plugin_email.commands.email as module

    async def fake_unread(_user_id: str):
        yield _fake_email()

    class _FakeItem:
        def __init__(self, count: int) -> None:
            self.count = count

        async def getName(self) -> str:
            return "鸡蛋"

    async def fake_get_item(_location: str, _user_id: str, count: int, _data: dict):
        return _FakeItem(count)

    monkeypatch.setattr(module, "get_unread_email", fake_unread)
    monkeypatch.setattr(module, "mark_email_read", AsyncMock(return_value=7))
    monkeypatch.setattr(module, "get_item", fake_get_item)
    monkeypatch.setattr(module, "lang", _FakeLang(_TEMPLATES))
    monkeypatch.setattr(module, "get_command_prefix", lambda: "/")
    return module


@pytest.fixture
def finish_mock() -> AsyncMock:
    return AsyncMock(side_effect=_Finished)


def _capture_sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """把 UniMessage.send 换成记录型实现，返回被发出的消息列表"""
    from nonebot_plugin_alconna import UniMessage

    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    monkeypatch.setattr(UniMessage, "send", fake_send)
    return sent


def _markdown_of(message: Any) -> str:
    """取出消息里的 markdown 文本"""
    from nonebot_plugin_alconna.uniseg import Text

    text = next(seg for seg in message if isinstance(seg, Text))
    assert any("markdown" in styles for styles in text.styles.values())
    return text.text


def _buttons_of(message: Any) -> list[Any]:
    """取出消息里键盘按钮"""
    from nonebot_plugin_alconna.uniseg import Keyboard

    return next(seg for seg in message if isinstance(seg, Keyboard)).children


@pytest.mark.asyncio
async def test_qq_email_list_is_markdown_with_keyboard(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：邮件列表以 markdown 文本发送，一键领取/全部已读改为键盘按钮"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Image

    module = email_env
    sent = _capture_sent(monkeypatch)
    monkeypatch.setattr(module.email, "finish", finish_mock)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), event=MagicMock(), user_id="10")

    assert len(sent) == 1
    message = sent[0]
    markdown = _markdown_of(message)
    assert markdown.startswith("## 邮件列表（共 1 封）")
    assert "### 测试邮件" in markdown
    assert "时间: 2026-10-14 08:30:00" in markdown
    assert "来自: Moonlark" in markdown
    assert "邮件 ID: 7" in markdown
    assert "第一行\n第二行" in markdown
    assert "包含的物品" in markdown
    assert "- 鸡蛋 ×3" in markdown
    assert not markdown.endswith("\n")
    assert [(str(button.label), button.text) for button in _buttons_of(message)] == [
        ("一键领取", "/email claim all"),
        ("全部已读", "/email read all"),
    ]
    # 按钮交给键盘后，markdown 里不再内嵌可点击指令，也不再展示用法说明
    assert "qqbot-cmd-input" not in markdown
    assert "email claim <" not in markdown
    assert "email read <" not in markdown
    assert "查看未读邮件" not in markdown
    # QQ 官方不再发送邮件列表渲染图
    assert not any(isinstance(seg, Image) for seg in message)
    # 带键盘的消息用 UniMessage.send 发送，随后单独 finish
    finish_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_qq_empty_email_list_shows_empty_hint(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：没有未读邮件时展示空列表提示，键盘按钮依然可用"""
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env

    async def empty_unread(_user_id: str):
        if False:  # pragma: no cover - 空的异步生成器
            yield None

    monkeypatch.setattr(module, "get_unread_email", empty_unread)
    sent = _capture_sent(monkeypatch)
    monkeypatch.setattr(module.email, "finish", finish_mock)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), event=MagicMock(), user_id="10")

    markdown = _markdown_of(sent[0])
    assert "## 邮件列表（共 0 封）" in markdown
    assert "> 暂无未读邮件。" in markdown
    assert "包含的物品" not in markdown
    assert [button.text for button in _buttons_of(sent[0])] == ["/email claim all", "/email read all"]


@pytest.mark.asyncio
async def test_qq_claimed_email_marked_in_markdown(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：已领取的邮件在 markdown 中带「已领取」标记"""
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env
    monkeypatch.setattr(module.email, "finish", finish_mock)

    async def claimed_unread(_user_id: str):
        yield _fake_email(is_claimed=True)

    monkeypatch.setattr(module, "get_unread_email", claimed_unread)
    sent = _capture_sent(monkeypatch)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), event=MagicMock(), user_id="10")

    assert "> 已领取" in _markdown_of(sent[0])


@pytest.mark.asyncio
async def test_qq_email_list_marks_emails_read(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：列出未读邮件后标记为已读"""
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env
    mark_read = AsyncMock(return_value=7)
    monkeypatch.setattr(module, "mark_email_read", mark_read)
    _capture_sent(monkeypatch)
    monkeypatch.setattr(module.email, "finish", finish_mock)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), event=MagicMock(), user_id="10")

    mark_read.assert_awaited_once_with(7, "10")


@pytest.mark.asyncio
async def test_other_adapter_email_still_image(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非 QQ 平台：仍发送渲染图消息，不带键盘"""
    from nonebot_plugin_alconna.uniseg import Image, Keyboard

    module = email_env
    monkeypatch.setattr(module, "render_template", AsyncMock(return_value=b"image-bytes"))
    monkeypatch.setattr(module.email, "finish", finish_mock)
    sent = _capture_sent(monkeypatch)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(), event=MagicMock(), user_id="10")

    (message,) = finish_mock.await_args.args
    image = next(seg for seg in message if isinstance(seg, Image))
    assert image.raw == b"image-bytes"
    assert not any(isinstance(seg, Keyboard) for seg in message)
    assert sent == []
