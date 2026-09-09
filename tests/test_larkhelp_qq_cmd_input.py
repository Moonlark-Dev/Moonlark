"""nonebot_plugin_larkhelp 的 QQ 指令组件（<qqbot-cmd-input>）属性值回归测试

1. urlencode：QQ 官方要求 <qqbot-cmd-input> 的 text/show 属性值需 urlencode 后传递，
   否则当用法包含尖括号占位符（如 `shop buy <编号> [数量]`）时平台返回
   "qqbot-cmd-input参数解析失败"（ActionFailed），即 /help shop 的线上报错。
2. 标签解析：平台解析标签属性时会按 markdown 处理其中文本，用法中 `[可选参数]`
   后紧跟 `(说明)`（如 `quick-math [--level <开始的等级>] (开始挑战)`）会被识别成
   链接导致整个标签无法解析、原文直接显示，因此把 (说明) 用法说明直接渲染在
   `<qqbot-cmd-input>` 标签外部，text/show 属性只携带指令本体。
"""

from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock
import re

import pytest

_SHOP_TEXT = {
    "help.usage1": "shop (查看商品列表)",
    "help.usage2": "shop buy <编号> [数量] (购买商品)",
    "help.usage3": "shop rank [--total] (积分排行榜)",
    "help.description": "商店与商品",
    "help.details": "查看商品并购买",
}

# 编码后的属性值中不允许出现的原始字符（% 允许出现，但只能是 %XX 编码形式）
_TAG_BREAKING_CHARS = "<>&\"'\n\r"


class _FakeUniMessage:
    """收集 .style(...).keyboard(...).send() 链式调用最终发送的 markdown"""

    sent: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self._text = ""

    def style(self, text: str, _style: str) -> "_FakeUniMessage":
        self._text = text
        return self

    def keyboard(self, *_buttons: object) -> "_FakeUniMessage":
        return self

    async def send(self, *_args: object, **_kwargs: object) -> None:
        self.sent.append(self._text)


@pytest.fixture
def larkhelp_env(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[tuple[str, tuple[object, ...]]]]:
    """写入手工 help_list，打桩 LangHelper.text（含真实模板渲染）与消息发送

    注意：插件导入必须在 fixture 内部进行（collection 阶段 nonebot 尚未初始化）。"""
    import nonebot_plugin_larkhelp.__main__ as module
    from nonebot_plugin_larklang.__main__ import LangHelper
    from nonebot_plugin_larkhelp.models import CommandHelp

    module.help_list = {
        "shop": CommandHelp(
            plugin="shop",
            description="help.description",
            details="help.details",
            usages=["help.usage1", "help.usage2", "help.usage3"],
            category="community",
        ),
    }
    _FakeUniMessage.sent.clear()

    lang_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fake_text(self: LangHelper, key: str, _user_id: str, *args: object) -> str:
        lang_calls.append((key, args))
        if self.plugin_name == "shop":
            return _SHOP_TEXT.get(key, f"shop::{key}")
        if key == "command.usage_item":
            return '<qqbot-cmd-input text="/{}" show="/{}" reference="false" /> {}'.format(*args)
        if key == "command.info_md":
            return "{} **{}**\n{}\n\n**用法**({}):\n{}".format(*args)
        if key == "menu_cat.item":
            return '- <qqbot-cmd-input text="/help {}" show="`{}`: {}" reference="false" />'.format(*args)
        if key == "menu_cat.md":
            return "{} **{}**的指令列表\n{}\n\n点击指令可以查看帮助！".format(*args)
        if key == "menu.category_item":
            return '<qqbot-cmd-input text="/menu {}" show="{} {}({} 个指令)" reference="false" />'.format(*args)
        if key == "menu.markdown":
            return "**Moonlark 功能导航**\n{}\n💡 **试试这个？**\n`{}`: {}".format(*args)
        return f"lang::{key}"

    monkeypatch.setattr(LangHelper, "text", fake_text)
    monkeypatch.setattr(module.help_cmd, "finish", AsyncMock())
    monkeypatch.setattr(module.menu_cmd, "finish", AsyncMock())
    monkeypatch.setattr(module, "get_command_prefix", lambda: "/")
    monkeypatch.setattr(module, "UniMessage", _FakeUniMessage)
    return module, lang_calls


def test_urlencode_cmd_encodes_tag_breaking_chars_only() -> None:
    """仅编码会破坏标签解析的保留字符，中文与空格保持原样"""
    from nonebot_plugin_larkhelp.__main__ import urlencode_cmd

    assert urlencode_cmd("shop buy <编号> [数量]") == "shop buy %3C编号%3E [数量]"
    assert urlencode_cmd("a&b\"c'd%") == "a%26b%22c%27d%25"
    assert urlencode_cmd("正常中文 空格") == "正常中文 空格"
    assert urlencode_cmd("line1\nline2\r\nline3") == "line1 line2 line3"


def test_split_usage_explanation_returns_command_and_explanation() -> None:
    """用法拆分为指令本体与末尾的 (说明)：说明文字渲染在标签外部"""
    from nonebot_plugin_larkhelp.__main__ import split_usage_explanation

    assert split_usage_explanation("quick-math [--level <开始的等级>] (开始挑战)") == (
        "quick-math [--level <开始的等级>]",
        "(开始挑战)",
    )
    assert split_usage_explanation("shop (查看商品列表)") == ("shop", "(查看商品列表)")
    assert split_usage_explanation("vote create [-g|--global] [-l|--last <持续(小时)>] [标题] (创建投票)") == (
        "vote create [-g|--global] [-l|--last <持续(小时)>] [标题]",
        "(创建投票)",
    )
    assert split_usage_explanation("help") == ("help", "")
    assert split_usage_explanation("  shop  (查看商品列表)  ") == ("shop", "(查看商品列表)")


def test_strip_usage_explanation_only_strips_trailing_parens() -> None:
    """text/show 属性只移除用法末尾的 (说明)，保留占位符内的括号注解（如 <持续(小时)>）"""
    from nonebot_plugin_larkhelp.__main__ import strip_usage_explanation

    assert strip_usage_explanation("quick-math [--level <开始的等级>] (开始挑战)") == (
        "quick-math [--level <开始的等级>]"
    )
    assert strip_usage_explanation("shop (查看商品列表)") == "shop"
    assert strip_usage_explanation("vote create [-g|--global] [-l|--last <持续(小时)>] [标题] (创建投票)") == (
        "vote create [-g|--global] [-l|--last <持续(小时)>] [标题]"
    )


def _assert_no_raw_breaking_chars(args: tuple[object, ...]) -> None:
    for value in args:
        assert not any(ch in str(value) for ch in _TAG_BREAKING_CHARS), args


@pytest.mark.asyncio
async def test_help_shop_qq_usage_item_is_urlencoded(larkhelp_env: object) -> None:
    """QQ 平台 /help shop：含尖括号占位符的用法在 <qqbot-cmd-input> 中必须被 urlencode，说明在标签外"""
    from nonebot.adapters.qq import Bot as QQBot

    module, lang_calls = larkhelp_env
    await module.help_command_handler(bot=MagicMock(spec=QQBot), command="shop", user_id="10")

    usage_items = [args for key, args in lang_calls if key == "command.usage_item"]
    assert usage_items == [
        ("shop", "shop", "(查看商品列表)"),
        ("shop buy %3C编号%3E [数量]", "shop buy %3C编号%3E [数量]", "(购买商品)"),
        ("shop rank [--total]", "shop rank [--total]", "(积分排行榜)"),
    ]
    for item in usage_items:
        _assert_no_raw_breaking_chars(item)

    assert len(module.UniMessage.sent) == 1
    markdown = module.UniMessage.sent[0]
    assert (
        '<qqbot-cmd-input text="/shop buy %3C编号%3E [数量]" '
        'show="/shop buy %3C编号%3E [数量]" reference="false" /> (购买商品)' in markdown
    )
    assert '<qqbot-cmd-input text="/shop" show="/shop" reference="false" /> (查看商品列表)' in markdown
    # 属性值内不允许出现未编码的尖括号
    assert 'text="/shop buy <编号>' not in markdown
    # 标签属性内不允许出现 [可选参数] 后跟 (说明)（会被平台当作链接解析导致标签无法解析），
    # 说明文字已移到标签外部，因此属性内 [XXX] 之后不再紧跟 (XXX)
    assert not re.search(r"<qqbot-cmd-input[^>]*\[[^\n\]]*\]\s*\(", markdown), markdown


@pytest.mark.asyncio
async def test_menu_category_qq_item_is_urlencoded(larkhelp_env: object) -> None:
    """QQ 平台 /menu <分类>：指令列表条目同样经过 urlencode（含描述中的特殊字符）"""
    from nonebot.adapters.qq import Bot as QQBot

    module, lang_calls = larkhelp_env
    await module.menu_category_handler(bot=MagicMock(spec=QQBot), category="community", user_id="10")

    items = [args for key, args in lang_calls if key == "menu_cat.item"]
    assert items
    for args in items:
        _assert_no_raw_breaking_chars(args)
    assert len(module.UniMessage.sent) == 1
    assert (
        '- <qqbot-cmd-input text="/help shop" show="`shop`: 商店与商品" reference="false" />'
        in module.UniMessage.sent[0]
    )


@pytest.mark.asyncio
async def test_send_markdown_menu_category_item_is_urlencoded(larkhelp_env: object) -> None:
    """QQ 平台 /menu：分类导航条目同样经过 urlencode"""
    module, lang_calls = larkhelp_env
    await module.send_markdown_menu("10")

    items = [args for key, args in lang_calls if key == "menu.category_item"]
    assert items
    for args in items:
        _assert_no_raw_breaking_chars(args)
    assert len(module.UniMessage.sent) == 1
    assert (
        '<qqbot-cmd-input text="/menu community" '
        'show="lang::menu.category_emoji.community lang::list.category.community(1 个指令)" reference="false" />'
        in module.UniMessage.sent[0]
    )
