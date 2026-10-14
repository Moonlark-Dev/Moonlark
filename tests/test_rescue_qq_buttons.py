"""rescue 指令在 QQ 官方机器人下的键盘按钮测试。

rescue 的支付方选择提示（rescue.pay_prompt_*）在 QQ 官方机器人下应该附带
由我支付 / 由对方支付 / 取消 三个键盘按钮；其他平台保持纯文本提示。
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 larkuser 的 LangHelper.text，避免依赖数据库读取语言文本。

    注意：插件导入必须在函数/fixture 内部进行（collection 阶段 nonebot 插件尚未加载）。
    """
    from nonebot_plugin_larkuser.lang import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


@pytest.mark.asyncio
async def test_build_pay_message_qqbot_adds_keyboard() -> None:
    """QQ 官方机器人下应返回带 keyboard 的 UniMessage，按钮回发 1/2/q"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard, UniMessage
    from nonebot_plugin_larkuser.matchers.rescue import build_pay_message

    message = await build_pay_message(bot=MagicMock(spec=QQBot), user_id="10", nickname="小明")

    assert isinstance(message, UniMessage)
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    buttons = list(keyboard.children)
    assert [button.text for button in buttons] == ["1", "2", "q"]
    assert [str(button.label) for button in buttons] == [
        "text::rescue.button_rescuer_pay",
        "text::rescue.button_target_pay",
        "text::rescue.button_quit",
    ]
    # markdown 正文应使用 pay_prompt_markdown 文案
    from nonebot_plugin_alconna import Text

    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == "text::rescue.pay_prompt_markdown"


@pytest.mark.asyncio
async def test_build_pay_message_non_qqbot_keeps_plain_text() -> None:
    """非 QQ 官方机器人（如 OneBot V11）保持纯文本提示"""
    from nonebot.adapters.onebot.v11 import Bot as V11Bot
    from nonebot_plugin_larkuser.matchers.rescue import build_pay_message

    message = await build_pay_message(bot=MagicMock(spec=V11Bot), user_id="10", nickname="小明")

    assert message == "text::rescue.pay_prompt"
