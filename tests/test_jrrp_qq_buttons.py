from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 jrrp 插件的 LangHelper.text，避免依赖数据库读取语言文本

    注意：插件导入必须在函数/fixture 内部进行（collection 阶段 nonebot 插件尚未加载）。
    """
    from nonebot_plugin_jrrp.lang import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


@pytest.mark.asyncio
async def test_build_jrrp_message_qq_prepends_at_and_adds_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人 jrrp 回复应保持原有文本并在最前面附加 @，同时附带三个键盘按钮"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage
    from nonebot_plugin_jrrp.__main__ import build_jrrp_message
    from nonebot_plugin_larkutils.command import config

    monkeypatch.setattr("nonebot_plugin_jrrp.__main__.get_luck_message", AsyncMock(return_value="你今天的人品值是: 66"))
    monkeypatch.setattr(config, "command_start", ["/"])

    message = await build_jrrp_message(bot=MagicMock(spec=QQBot), user_id="10")

    assert isinstance(message, UniMessage)
    # 文本保持原有内容，且最前面附加 @ (qqbot-at-user)
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == '<qqbot-at-user id="10" />你今天的人品值是: 66'
    assert any("markdown" in styles for styles in text.styles.values())
    # 键盘包含 幸运星/倒霉蛋/重新抽取 三个 enter 按钮
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    buttons = list(keyboard.children)
    assert [button.text for button in buttons] == ["/jrrp r", "/jrrp rr", "/jrrp reroll"]
    assert [str(button.label) for button in buttons] == [
        "text::button.lucky_star",
        "text::button.unlucky_one",
        "text::button.reroll",
    ]


@pytest.mark.asyncio
async def test_build_jrrp_message_plain_text_on_other_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 平台应保持原有纯文本消息（由 matcher.send(at_sender=True) 附加 @）"""
    from nonebot_plugin_jrrp.__main__ import build_jrrp_message

    monkeypatch.setattr("nonebot_plugin_jrrp.__main__.get_luck_message", AsyncMock(return_value="你今天的人品值是: 66"))

    message = await build_jrrp_message(bot=MagicMock(), user_id="10")

    assert message == "你今天的人品值是: 66"
