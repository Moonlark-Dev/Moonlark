"""QQ 官方适配器下「群聊含 @ 消息自动转 Markdown」的回归测试。"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_qq_bot() -> Any:
    from nonebot.adapters.qq import Bot as QQBot

    bot = MagicMock(spec=QQBot)
    bot.self_id = "102000001"
    bot.adapter = MagicMock()
    bot.adapter.get_name.return_value = "QQ"
    return bot


@pytest.mark.asyncio
async def test_text_with_mention_escapes_markdown() -> None:
    """纯文本段转入 Markdown 时必须转义特殊字符，避免尖括号占位符或星号破坏渲染。"""
    from nonebot.adapters.qq.message import MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    message = MessageSegment.mention_user("member_openid") + MessageSegment.text("用法: /cmd <数字> *加粗*")
    converted = await convert_group_message(message)

    assert converted is not None
    assert converted["mention_user"] == []
    content = converted["markdown"][0].data["markdown"].content
    assert content == '<qqbot-at-user id="member_openid" />用法: /cmd \\<数字\\> \\*加粗\\*'


@pytest.mark.asyncio
async def test_standalone_at_line_inserts_blank_line() -> None:
    """独占一行的 <qqbot-at-user /> 后接单换行时应自动补成双换行，闭合 CommonMark HTML 块。"""
    from nonebot.adapters.qq.message import MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    message = MessageSegment.mention_user("member_openid") + MessageSegment.text("\n第一行 *文本*\n第二行")
    converted = await convert_group_message(message)

    assert converted is not None
    content = converted["markdown"][0].data["markdown"].content
    assert content == '<qqbot-at-user id="member_openid" />\n\n第一行 \\*文本\\*\n第二行'


@pytest.mark.asyncio
async def test_mention_everyone_and_emoji_converted() -> None:
    """全体成员提及与系统表情段应一并转为 QQ Markdown 标签语法。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    message = Message(
        [
            MessageSegment.mention_everyone(),
            MessageSegment.emoji("4"),
            MessageSegment.text("全体注意"),
        ],
    )
    converted = await convert_group_message(message)

    assert converted is not None
    assert converted["mention_everyone"] == []
    assert converted["markdown"][0].data["markdown"].content == "<qqbot-at-everyone /><emoji:4>全体注意"


@pytest.mark.asyncio
async def test_existing_markdown_not_double_escaped_and_preserves_buttons() -> None:
    """已有 markdown 段保持原样不重复转义，键盘与引用段原样保留。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    button_seg = MessageSegment("$qq:button", {"button": "ok"})
    message = Message(
        [
            MessageSegment.mention_user("member_openid"),
            MessageSegment.markdown("**bold**"),
            button_seg,
        ],
    )
    converted = await convert_group_message(message)

    assert converted is not None
    assert converted["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid" />**bold**'
    assert converted["$qq:button"] == [button_seg]


@pytest.mark.asyncio
async def test_already_mentioned_user_is_not_duplicated() -> None:
    """消息自身已含目标用户的 <qqbot-at-user> 标签时，at_user_id 不应重复前置 @。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    message = Message([MessageSegment.markdown('<qqbot-at-user id="member_openid" />**hi**')])
    converted = await convert_group_message(message, at_user_id="member_openid")

    assert converted is None


@pytest.mark.asyncio
async def test_message_without_mention_is_untouched() -> None:
    """不含 @ 的普通文本消息应返回 None，保持纯文本发送。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    assert await convert_group_message(Message([MessageSegment.text("hello")])) is None


@pytest.mark.asyncio
async def test_file_image_with_at_uploads_and_embeds_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """本地二进制图片（file_image）带 @ 时应上传至 QQ 素材库并内嵌到 Markdown。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    upload_mock = AsyncMock(return_value="![text #120px #80px](qqbot-media://image/v1/tok)")
    monkeypatch.setattr(qq_at_markdown, "create_image_markdown", upload_mock)

    bot = _make_qq_bot()
    message = Message([MessageSegment.file_image(b"png-bytes")])
    converted = await qq_at_markdown.convert_group_message(message, bot=bot, at_user_id="member_openid")

    upload_mock.assert_awaited_once_with(b"png-bytes", bot)
    assert converted is not None
    assert converted["file_image"] == []
    assert converted["markdown"][0].data["markdown"].content == (
        '<qqbot-at-user id="member_openid" />![text #120px #80px](qqbot-media://image/v1/tok)'
    )


@pytest.mark.asyncio
async def test_url_image_with_mention_downloads_and_embeds_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """外网图片 URL（如 /waifu 头像）带 @ 时应经 SSRF 校验下载后上传为 Markdown 图片。"""
    from nonebot.adapters.qq.message import MessageSegment
    from nonebot.drivers import Response
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    monkeypatch.setattr(qq_at_markdown, "resolve_internal", AsyncMock(return_value=False))
    upload_mock = AsyncMock(return_value="![text #100px #100px](qqbot-media://image/v1/avatar)")
    monkeypatch.setattr(qq_at_markdown, "create_image_markdown", upload_mock)

    bot = _make_qq_bot()
    bot.adapter.request = AsyncMock(return_value=Response(200, content=b"avatar-bytes"))

    message = (
        MessageSegment.text("今日群友老婆是 ")
        + MessageSegment.mention_user("wife_openid")
        + MessageSegment.image("https://q.qlogo.cn/avatar.png")
    )
    converted = await qq_at_markdown.convert_group_message(message, bot=bot)

    upload_mock.assert_awaited_once_with(b"avatar-bytes", bot)
    assert converted is not None
    assert converted["image"] == []
    assert converted["mention_user"] == []
    assert converted["markdown"][0].data["markdown"].content == (
        '今日群友老婆是 <qqbot-at-user id="wife_openid" />![text #100px #100px](qqbot-media://image/v1/avatar)'
    )


@pytest.mark.asyncio
async def test_image_failure_or_internal_url_falls_back_without_raw_mention_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """图片为内网地址或上传失败时，应剥离 mention_user 回退原消息，既不丢图也不泄露裸标签。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    monkeypatch.setattr(qq_at_markdown, "resolve_internal", AsyncMock(return_value=True))
    bot = _make_qq_bot()

    msg_with_mention = (
        MessageSegment.text("老婆是 ")
        + MessageSegment.mention_user("wife_openid")
        + MessageSegment.image("http://127.0.0.1/secret.png")
    )
    fallback = await qq_at_markdown.convert_group_message(msg_with_mention, bot=bot)
    assert fallback is not None
    assert fallback["mention_user"] == []
    assert len(fallback["image"]) == 1
    assert fallback.extract_plain_text() == "老婆是 "

    monkeypatch.setattr(qq_at_markdown, "create_image_markdown", AsyncMock(side_effect=RuntimeError("upload failed")))
    pure_file_img = Message([MessageSegment.file_image(b"raw-img")])
    assert await qq_at_markdown.convert_group_message(pure_file_img, bot=bot, at_user_id="member_openid") is None


@pytest.mark.asyncio
async def test_unsupported_rich_segment_strips_mention_fallback() -> None:
    """含 ARK 等无法内嵌的富媒体段时应剥离提及段后回退原消息。"""
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import convert_group_message

    ark_seg = MessageSegment("ark", {"ark": {"template_id": 23}})
    message = Message([MessageSegment.mention_user("member_openid"), ark_seg])
    fallback = await convert_group_message(message)

    assert fallback is not None
    assert fallback["mention_user"] == []
    assert fallback["ark"] == [ark_seg]


@pytest.mark.asyncio
async def test_skip_at_markdown_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """skip_at_markdown() 上下文内应跳过转换，退出后恢复自动转换。"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
    from nonebot.adapters.qq.message import MessageSegment
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown
    from nonebot_plugin_larkutils import skip_at_markdown

    raw_send = AsyncMock(return_value=None)
    monkeypatch.setattr(qq_at_markdown, "_raw_bot_send", raw_send)

    bot = _make_qq_bot()
    event = MagicMock(spec=GroupAtMessageCreateEvent)
    event.get_user_id.return_value = "member_openid"
    msg = MessageSegment.mention_user("member_openid") + MessageSegment.text("hello")

    with skip_at_markdown():
        assert await qq_at_markdown.convert_group_message(msg) is None
        await QQBot.send(bot, event, "plain", at_sender=True)

    assert raw_send.call_args.args[2] == "plain"
    assert raw_send.call_args.kwargs == {"at_sender": True}

    await QQBot.send(bot, event, "plain", at_sender=True)
    sent_after = raw_send.call_args.args[2]
    assert sent_after["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid" />plain'


@pytest.mark.asyncio
async def test_bot_send_covers_group_events_and_excludes_c2c(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQBot.send（matcher.send / lang.send 真实路径）应覆盖公域/私域群事件与群按钮交互，排除 C2C。"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import (
        C2CMessageCreateEvent,
        GroupAtMessageCreateEvent,
        GroupMessageCreateEvent,
        InteractionCreateEvent,
    )
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    raw_send = AsyncMock(return_value=None)
    monkeypatch.setattr(qq_at_markdown, "_raw_bot_send", raw_send)
    bot = _make_qq_bot()

    # 1. 公域群 @ 事件（GROUP_AT_MESSAGE_CREATE）+ 纯字符串含尖括号文本
    group_at_event = MagicMock(spec=GroupAtMessageCreateEvent)
    group_at_event.get_user_id.return_value = "member_openid_1"
    await QQBot.send(bot, group_at_event, "你好 <@123>", at_sender=True)
    sent_msg = raw_send.call_args.args[2]
    assert "at_sender" not in raw_send.call_args.kwargs
    assert sent_msg["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid_1" />你好 \\<@123\\>'

    # 2. 全量群消息事件（GROUP_MESSAGE_CREATE）
    group_msg_event = MagicMock(spec=GroupMessageCreateEvent)
    group_msg_event.get_user_id.return_value = "member_openid_2"
    await QQBot.send(bot, group_msg_event, "收到", at_sender=True)
    sent_group_msg = raw_send.call_args.args[2]
    assert sent_group_msg["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid_2" />收到'

    # 3. 群聊按钮交互事件（group_openid 非空）与单聊按钮交互事件（group_openid 为空）
    group_inter = MagicMock(spec=InteractionCreateEvent)
    group_inter.group_openid = "group_openid_1"
    group_inter.get_user_id.return_value = "member_openid_3"
    await QQBot.send(bot, group_inter, "按钮响应", at_sender=True)
    sent_inter_msg = raw_send.call_args.args[2]
    assert sent_inter_msg["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid_3" />按钮响应'

    c2c_inter = MagicMock(spec=InteractionCreateEvent)
    c2c_inter.group_openid = None
    c2c_inter.get_user_id.return_value = "user_openid_1"
    await QQBot.send(bot, c2c_inter, "单聊按钮", at_sender=True)
    assert raw_send.call_args.args[2] == "单聊按钮"

    # 4. C2C 私聊事件保持原样，不注入 <qqbot-at-user>
    c2c_event = MagicMock(spec=C2CMessageCreateEvent)
    c2c_event.get_user_id.return_value = "user_openid_1"
    await QQBot.send(bot, c2c_event, "私聊文本", at_sender=True)
    assert raw_send.call_args.args[2] == "私聊文本"


@pytest.mark.asyncio
async def test_bot_send_to_group_converts_mentions(monkeypatch: pytest.MonkeyPatch) -> None:
    """直接调用 QQBot.send_to_group 发送带提及的消息时同样应转为 Markdown。"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.message import MessageSegment
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    raw_send_to_group = AsyncMock(return_value=None)
    monkeypatch.setattr(qq_at_markdown, "_raw_send_to_group", raw_send_to_group)
    bot = _make_qq_bot()

    msg = MessageSegment.mention_user("member_openid") + MessageSegment.text("主动消息 *提示*")
    await QQBot.send_to_group(bot, group_openid="group_openid", message=msg)

    sent = raw_send_to_group.call_args.kwargs["message"]
    assert sent["mention_user"] == []
    assert sent["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid" />主动消息 \\*提示\\*'


@pytest.mark.asyncio
async def test_exporter_converts_group_target_and_keeps_private_or_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """UniMessage.send / QQMessageExporter.send_to 应对群聊转换 Markdown，对私聊和频道保持原样。"""
    from nonebot.adapters.qq.message import MessageSegment
    from nonebot_plugin_alconna import Target, UniMessage
    from nonebot_plugin_alconna.uniseg.adapters.qq.exporter import QQMessageExporter
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    raw_exporter_send = AsyncMock(return_value=None)
    monkeypatch.setattr(qq_at_markdown, "_raw_exporter_send_to", raw_exporter_send)

    bot = _make_qq_bot()
    uni_msg = UniMessage().at("member_openid").text(" @你好 <tag>")
    await uni_msg.send(target=Target.group("group_openid", adapter="QQ"), bot=bot)
    sent_group = raw_exporter_send.call_args.args[2]
    assert sent_group["mention_user"] == []
    assert sent_group["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid" /> @你好 \\<tag\\>'

    exporter = QQMessageExporter()

    private_msg = MessageSegment.mention_user("user_openid") + MessageSegment.text("hi")
    await exporter.send_to(Target.user("user_openid", adapter="QQ"), bot, private_msg)
    assert raw_exporter_send.call_args.args[2] is private_msg

    channel_msg = MessageSegment.mention_user("guild_uid") + MessageSegment.text("hi")
    await exporter.send_to(Target("channel_1", parent_id="guild_1", channel=True, adapter="QQ"), bot, channel_msg)
    assert raw_exporter_send.call_args.args[2] is channel_msg


@pytest.mark.asyncio
async def test_panel_end_to_end_group_markdown_and_c2c_native_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """/panel 无需特判代码：QQ 群聊下自动上传图片并内嵌 @ Markdown，C2C 下保持原生 file_image。"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import C2CMessageCreateEvent, GroupAtMessageCreateEvent
    from nonebot.matcher import current_bot
    import nonebot_plugin_larkuser.matchers.panel as panel
    import nonebot_plugin_larkutils.qq_at_markdown as qq_at_markdown

    user = MagicMock()
    user.get_level.return_value = 2
    user.experience = 10
    user.get_nickname.return_value = "nick"
    user.get_base64_avatar.return_value = "avatar"
    user.get_vimcoin.return_value = 1.0
    user.get_display_fav.return_value = "fav"
    user.get_fav_level = AsyncMock(return_value="Lv1")
    user.get_health.return_value = 100
    monkeypatch.setattr(panel, "get_user", AsyncMock(return_value=user))
    monkeypatch.setattr(panel, "render_template", AsyncMock(return_value=b"panel-png"))

    upload_mock = AsyncMock(return_value="![panel](qqbot-media://panel)")
    monkeypatch.setattr(qq_at_markdown, "create_image_markdown", upload_mock)

    async def fake_text(key: str, _user_id: str, *_args: object) -> str:
        return key

    monkeypatch.setattr(panel.lang, "text", fake_text)

    raw_send = AsyncMock(return_value=None)
    monkeypatch.setattr(qq_at_markdown, "_raw_bot_send", raw_send)

    bot = _make_qq_bot()
    group_event = MagicMock(spec=GroupAtMessageCreateEvent)
    group_event.get_user_id.return_value = "member_openid"

    matcher = MagicMock()

    async def finish_group(msg: Any = None, **kwargs: Any) -> None:
        await QQBot.send(bot, group_event, msg, **kwargs)

    matcher.finish = AsyncMock(side_effect=finish_group)

    token = current_bot.set(bot)
    try:
        await panel.get_user_info(matcher, "10")
    finally:
        current_bot.reset(token)

    upload_mock.assert_awaited_once_with(b"panel-png", bot)
    sent_group = raw_send.call_args.args[2]
    assert sent_group["file_image"] == []
    assert sent_group["markdown"][0].data["markdown"].content == (
        '<qqbot-at-user id="member_openid" />![panel](qqbot-media://panel)'
    )

    # C2C 单聊：不调用素材上传，直接发原生 file_image
    upload_mock.reset_mock()
    c2c_event = MagicMock(spec=C2CMessageCreateEvent)
    c2c_event.get_user_id.return_value = "user_openid"

    async def finish_c2c(msg: Any = None, **kwargs: Any) -> None:
        await QQBot.send(bot, c2c_event, msg, **kwargs)

    matcher.finish = AsyncMock(side_effect=finish_c2c)
    token = current_bot.set(bot)
    try:
        await panel.get_user_info(matcher, "10")
    finally:
        current_bot.reset(token)

    upload_mock.assert_not_awaited()
    sent_c2c = raw_send.call_args.args[2]
    assert len(sent_c2c["file_image"]) == 1
    assert sent_c2c["markdown"] == []
