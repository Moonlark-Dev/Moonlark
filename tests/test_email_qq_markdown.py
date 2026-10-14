"""nonebot_plugin_email 的 QQ 官方 markdown 展示回归测试。

QQ 官方机器人下，未读邮件列表完全以 markdown 文本展示：不渲染图片、
不附带键盘按钮，一键领取/全部已读内嵌为 <qqbot-cmd-input>；
其余平台仍只发送邮件列表渲染图。
"""

import datetime
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
    "email_list.action_claim_all_md": (
        '- <qqbot-cmd-input text="{__prefix__}email claim all" show="一键领取" reference="false" />'
    ),
    "email_list.action_read_all_md": (
        '- <qqbot-cmd-input text="{__prefix__}email read all" show="全部已读" reference="false" />'
    ),
    "email_list.footer_md": "使用 {__prefix__}email claim <邮件 ID> / {__prefix__}email read <邮件 ID>",
}


class _FakeUniMessage:
    """模拟仅用于 QQ 分支的 UniMessage：markdown 文本 + 禁止 image/keyboard"""

    def __init__(self) -> None:
        self.markdown = ""

    def style(self, text: str, _style: str) -> "_FakeUniMessage":
        self.markdown = text
        return self

    def keyboard(self, *_args: object) -> "_FakeUniMessage":
        raise AssertionError("QQ 官方邮件列表不应附带键盘按钮")

    def image(self, **kwargs: object) -> "_FakeUniMessage":
        raise AssertionError("QQ 官方邮件列表不应发送渲染图片")


class _FakeImageMessage:
    """模拟非 QQ 平台的 UniMessage().image(raw=...)"""

    def __init__(self) -> None:
        self.image_raw = None

    def image(self, raw: bytes | None = None) -> "_FakeImageMessage":
        self.image_raw = raw
        return self


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
    return module


@pytest.fixture
def finish_mock() -> AsyncMock:
    return AsyncMock(side_effect=_Finished)


@pytest.mark.asyncio
async def test_qq_email_list_is_markdown_without_keyboard_or_image(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：邮件列表以纯 markdown 文本结束处理器，不发送图片、不发送键盘"""
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env
    messages: list[_FakeUniMessage] = []

    def fake_unimessage(*_args: object, **_kwargs: object) -> _FakeUniMessage:
        message = _FakeUniMessage()
        messages.append(message)
        return message

    monkeypatch.setattr(module, "UniMessage", fake_unimessage)
    monkeypatch.setattr(module.email, "finish", finish_mock)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), user_id="10")

    assert len(messages) == 1
    markdown = messages[0].markdown
    assert markdown.startswith("## 邮件列表（共 1 封）")
    assert "### 测试邮件" in markdown
    assert "时间: 2026-10-14 08:30:00" in markdown
    assert "来自: Moonlark" in markdown
    assert "邮件 ID: 7" in markdown
    assert "第一行\n第二行" in markdown
    assert "包含的物品" in markdown
    assert "- 鸡蛋 ×3" in markdown
    assert '<qqbot-cmd-input text="/email claim all" show="一键领取" reference="false" />' in markdown
    assert '<qqbot-cmd-input text="/email read all" show="全部已读" reference="false" />' in markdown
    finish_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_qq_empty_email_list_shows_empty_hint(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：没有未读邮件时展示空列表提示与可点击操作"""
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env

    async def empty_unread(_user_id: str):
        if False:  # pragma: no cover - 空的异步生成器
            yield None

    monkeypatch.setattr(module, "get_unread_email", empty_unread)
    messages: list[_FakeUniMessage] = []

    def fake_unimessage(*_args: object, **_kwargs: object) -> _FakeUniMessage:
        message = _FakeUniMessage()
        messages.append(message)
        return message

    monkeypatch.setattr(module, "UniMessage", fake_unimessage)
    monkeypatch.setattr(module.email, "finish", finish_mock)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), user_id="10")

    markdown = messages[0].markdown
    assert "## 邮件列表（共 0 封）" in markdown
    assert "> 暂无未读邮件。" in markdown
    assert "包含的物品" not in markdown


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
    messages: list[_FakeUniMessage] = []

    def fake_unimessage(*_args: object, **_kwargs: object) -> _FakeUniMessage:
        message = _FakeUniMessage()
        messages.append(message)
        return message

    monkeypatch.setattr(module, "UniMessage", fake_unimessage)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), user_id="10")

    assert "> 已领取" in messages[0].markdown


@pytest.mark.asyncio
async def test_qq_email_list_marks_emails_read(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QQ 官方：列出未读邮件后标记为已读"""
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env
    mark_read = AsyncMock(return_value=7)
    monkeypatch.setattr(module, "mark_email_read", mark_read)
    monkeypatch.setattr(module, "UniMessage", lambda *_args, **_kwargs: _FakeUniMessage())
    monkeypatch.setattr(module.email, "finish", finish_mock)

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(spec=QQBot), user_id="10")

    mark_read.assert_awaited_once_with(7, "10")


@pytest.mark.asyncio
async def test_other_adapter_email_still_image(
    email_env, finish_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非 QQ 平台：仍发送渲染图消息"""
    module = email_env
    monkeypatch.setattr(module, "render_template", AsyncMock(return_value=b"image-bytes"))
    monkeypatch.setattr(module.email, "finish", finish_mock)
    monkeypatch.setattr(module, "UniMessage", lambda *_args, **_kwargs: _FakeImageMessage())

    with pytest.raises(_Finished):
        await module._(bot=MagicMock(), user_id="10")

    (message,) = finish_mock.await_args.args
    assert message.image_raw == b"image-bytes"
