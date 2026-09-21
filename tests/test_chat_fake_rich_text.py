"""伪装富文本检测测试

用户可以直接发送 ``[图片(img_1)]`` 这类与 Moonlark 内部占位符格式完全相同的纯文本，
仅从格式化后的文本无法与真实消息段区分，因此需要在格式化消息时把它们检测出来并提示模型。
"""

from __future__ import annotations


def test_detects_image_placeholder() -> None:
    from nonebot_plugin_chat.utils.rich_text import find_fake_rich_text

    assert find_fake_rich_text("你看 [图片(img_1)]") == ["[图片(img_1)]"]


def test_detects_rich_text_placeholders_of_all_kinds() -> None:
    from nonebot_plugin_chat.utils.rich_text import find_fake_rich_text

    text = (
        "[图片(img_1): 一只猫] [图片: 描述] [视频(a.mp4): 内容] [文件(b.txt): 文本] "
        '[回复: 你好] [合并转发：消息列表] [特殊消息: {"type": "poke"}] '
        "[戳一戳] [表情: 微笑] [emoji:123]"
    )
    assert find_fake_rich_text(text) == [
        "[图片(img_1): 一只猫]",
        "[图片: 描述]",
        "[视频(a.mp4): 内容]",
        "[文件(b.txt): 文本]",
        "[回复: 你好]",
        "[合并转发：消息列表]",
        '[特殊消息: {"type": "poke"}]',
        "[戳一戳]",
        "[表情: 微笑]",
        "[emoji:123]",
    ]


def test_ignores_plain_text() -> None:
    from nonebot_plugin_chat.utils.rich_text import find_fake_rich_text

    assert find_fake_rich_text("今天天气不错，我们去公园吧") == []
    assert find_fake_rich_text("[链接](https://example.com)") == []
    assert find_fake_rich_text("") == []


def test_deduplicates_and_keeps_order() -> None:
    from nonebot_plugin_chat.utils.rich_text import find_fake_rich_text

    assert find_fake_rich_text("[图片(img_2)] 和 [图片(img_1)] 再加 [图片(img_2)]") == [
        "[图片(img_2)]",
        "[图片(img_1)]",
    ]


def test_does_not_match_across_lines() -> None:
    from nonebot_plugin_chat.utils.rich_text import find_fake_rich_text

    assert find_fake_rich_text("[图片(img_1)\n后面还有内容]") == []


async def test_parser_collects_only_from_text_segments() -> None:
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_chat.utils.message import MessageParser

    parser = MessageParser(UniMessage(), None, None, {}, "zh_hans")  # type: ignore[arg-type]
    await parser.parse_segment(Text("[图片(img_1)] 你好"))
    await parser.parse_segment(Text("普通文本"))
    await parser.parse_segment(Text("[戳一戳]"))

    assert parser.fake_rich_text == ["[图片(img_1)]", "[戳一戳]"]


async def test_parser_shares_collection_with_nested_callers() -> None:
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_chat.utils.message import MessageParser

    collected: list[str] = []
    parser = MessageParser(UniMessage(), None, None, {}, "zh_hans", fake_rich_text=collected)  # type: ignore[arg-type]
    await parser.parse_segment(Text("[图片(img_9)]"))

    assert collected == ["[图片(img_9)]"]
    assert parser.fake_rich_text is collected


async def test_additional_info_warns_about_fake_rich_text() -> None:
    from nonebot_plugin_openai import get_message_text

    rendered = await get_message_text(
        "chat_message.md.jinja",
        token=None,
        nickname="小明",
        display_fav=10,
        fav_level=20,
        note_text="暂无",
        tiredness=5,
        state="当前状态：\n心情：calm",
        pending_notes=None,
        fake_rich_text=["[图片(img_1)]"],
    )

    assert "[图片(img_1)]" in rendered
    assert "纯文本" in rendered


async def test_additional_info_has_no_warning_without_fake_rich_text() -> None:
    from nonebot_plugin_openai import get_message_text

    rendered = await get_message_text(
        "chat_message.md.jinja",
        token=None,
        nickname="小明",
        display_fav=10,
        fav_level=20,
        note_text="暂无",
        tiredness=5,
        state="当前状态：\n心情：calm",
        pending_notes=None,
        fake_rich_text=None,
    )

    assert "纯文本" not in rendered
