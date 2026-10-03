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
    # 非 C2C 场景下没有 event，退回不带 @ 的纯 markdown，文本保持原有内容
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == "你今天的人品值是: 66"
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
async def test_build_jrrp_message_qq_group_at_uses_adapter_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """群聊 @ 必须用适配器原生 ID（member_openid），而不是 larkutils 的主账号 ID

    ``<qqbot-at-user>`` 只认适配器原生 ID；传 larkutils 的主账号 ID（QQ 号）会 @ 到
    一个在开放平台 openid 体系里并不存在的用户。
    """
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
    from nonebot_plugin_alconna import Text
    from nonebot_plugin_jrrp.__main__ import build_jrrp_message
    from nonebot_plugin_larkutils.command import config

    monkeypatch.setattr("nonebot_plugin_jrrp.__main__.get_luck_message", AsyncMock(return_value="你今天的人品值是: 66"))
    monkeypatch.setattr(config, "command_start", ["/"])

    event = MagicMock(spec=GroupAtMessageCreateEvent)
    event.get_user_id.return_value = "MEMBER_OPENID_ABC"

    # user_id 是 larkutils 的主账号 ID，与适配器原生 ID 不同
    message = await build_jrrp_message(bot=MagicMock(spec=QQBot), user_id="10001", event=event)

    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == '<qqbot-at-user id="MEMBER_OPENID_ABC" />你今天的人品值是: 66'
    # 主账号 ID 不能出现在 @ 标签里
    assert 'id="10001"' not in text.text


@pytest.mark.asyncio
async def test_build_jrrp_message_c2c_skips_at_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2C 单聊消息不支持 qqbot-at-user 提及，QQ 官方机器人下应跳过 @ 前缀"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import C2CMessageCreateEvent
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_jrrp.__main__ import build_jrrp_message
    from nonebot_plugin_larkutils.command import config

    monkeypatch.setattr("nonebot_plugin_jrrp.__main__.get_luck_message", AsyncMock(return_value="你今天的人品值是: 66"))
    monkeypatch.setattr(config, "command_start", ["/"])

    message = await build_jrrp_message(
        bot=MagicMock(spec=QQBot),
        user_id="10",
        event=MagicMock(spec=C2CMessageCreateEvent),
    )

    assert isinstance(message, UniMessage)
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == "你今天的人品值是: 66"


@pytest.mark.asyncio
async def test_build_jrrp_message_plain_text_on_other_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 平台应保持原有纯文本消息（由 matcher.send(at_sender=True) 附加 @）"""
    from nonebot_plugin_jrrp.__main__ import build_jrrp_message

    monkeypatch.setattr("nonebot_plugin_jrrp.__main__.get_luck_message", AsyncMock(return_value="你今天的人品值是: 66"))

    message = await build_jrrp_message(bot=MagicMock(), user_id="10")

    assert message == "你今天的人品值是: 66"
