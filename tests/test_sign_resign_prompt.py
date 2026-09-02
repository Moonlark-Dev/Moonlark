from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 sign 插件的 LangHelper.text，避免依赖数据库读取语言文本

    注意：插件导入必须在函数/fixture 内部进行（collection 阶段 nonebot 插件尚未加载）。
    """
    from nonebot_plugin_sign.lang import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


def _make_handler(bot: MagicMock):
    from nonebot_plugin_sign.__main__ import SignHandler

    handler = SignHandler(user_id="10", bot=bot, event=MagicMock(), matcher=MagicMock())
    handler._missed_days = 3  # ruff: ignore[private-member-access]
    return handler


@pytest.mark.asyncio
async def test_build_resign_prompt_qq_uses_markdown_keyboard() -> None:
    """QQ 官方机器人应返回 markdown 消息并附带是/否键盘按钮，替代文本 [y/n] 提示"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage

    handler = _make_handler(bot=MagicMock(spec=QQBot))
    message = await handler.build_resign_prompt(needed=90)

    assert isinstance(message, UniMessage)
    # 消息体为 markdown 样式的补签提示
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == "text::resign.prompt_markdown"
    assert any("markdown" in styles for styles in text.styles.values())
    # 键盘包含 是(y) / 否(n) 两个 enter 按钮
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    buttons = list(keyboard.children)
    assert [button.text for button in buttons] == ["y", "n"]
    assert [str(button.label) for button in buttons] == ["text::resign.button_yes", "text::resign.button_no"]


@pytest.mark.asyncio
async def test_build_resign_prompt_plain_text_on_other_adapters() -> None:
    """非 QQ 平台应保持原有文本 [y/n] 提示"""
    handler = _make_handler(bot=MagicMock())
    message = await handler.build_resign_prompt(needed=90)

    assert message == "text::resign.prompt"


@pytest.mark.asyncio
async def test_build_button_invite_and_jrrp(monkeypatch: pytest.MonkeyPatch) -> None:
    """签到结果键盘应始终包含 我也要签到 与 今日人品 按钮"""
    from nonebot_plugin_sign.__main__ import config

    handler = _make_handler(bot=MagicMock())
    monkeypatch.setattr("nonebot_plugin_sign.__main__.get_unread_email_count", AsyncMock(return_value=0))
    monkeypatch.setattr(config, "command_start", ["/"])
    buttons = await handler.build_button()

    assert isinstance(buttons, list)
    assert [str(button.label) for button in buttons] == ["text::button.invite", "text::button.jrrp"]
    assert [button.text for button in buttons] == ["/sign", "/jrrp"]


@pytest.mark.asyncio
async def test_build_button_adds_email_when_unread(monkeypatch: pytest.MonkeyPatch) -> None:
    """存在未读邮件时键盘应额外包含 查看邮件 按钮"""
    from nonebot_plugin_sign.__main__ import config

    handler = _make_handler(bot=MagicMock())
    monkeypatch.setattr("nonebot_plugin_sign.__main__.get_unread_email_count", AsyncMock(return_value=2))
    monkeypatch.setattr(config, "command_start", ["/"])
    buttons = await handler.build_button()

    assert len(buttons) == 3
    assert str(buttons[-1].label) == "text::button.email"
    assert buttons[-1].text == "/email"
