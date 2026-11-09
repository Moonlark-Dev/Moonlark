"""QQ 官方适配器下「带 at 的消息转 markdown」的回归测试。

QQ 官方机器人不再支持在非 markdown 消息里使用 at，larkutils 接管 QQ 消息导出器，
把群聊里含 at 的普通消息改写为 markdown；图片等富媒体消息保持原样，chat 插件
通过 ``skip_at_markdown()`` 显式跳过转换。
"""

from unittest.mock import AsyncMock

import pytest


def _mention_message(text: str = "你好") -> "object":
    from nonebot.adapters.qq.message import MessageSegment

    return MessageSegment.mention_user("member_openid") + MessageSegment.text(text)


def test_message_with_mention_becomes_markdown() -> None:
    from nonebot_plugin_larkutils.qq_at_markdown import _message_to_markdown

    message = _mention_message("hello")
    converted = _message_to_markdown(message)

    assert converted is not None
    assert converted["mention_user"] == []
    markdown = converted["markdown"][0]
    assert markdown.data["markdown"].content == '<qqbot-at-user id="member_openid" />hello'


def test_message_without_mention_is_untouched() -> None:
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import _message_to_markdown

    assert _message_to_markdown(Message([MessageSegment.text("hello")])) is None


def test_media_message_with_mention_is_untouched() -> None:
    """图片消息（msg_type=7）不能带 markdown，强行改写会丢图。"""
    from nonebot.adapters.qq.message import MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import _message_to_markdown

    message = MessageSegment.mention_user("member_openid") + MessageSegment.image("https://example.com/a.png")
    assert _message_to_markdown(message) is None


def test_already_markdown_message_keeps_mention() -> None:
    from nonebot.adapters.qq.message import MessageSegment
    from nonebot_plugin_larkutils.qq_at_markdown import _message_to_markdown

    message = MessageSegment.mention_user("member_openid") + MessageSegment.markdown("**hi**")
    converted = _message_to_markdown(message)

    assert converted is not None
    assert converted["mention_user"] == []
    assert converted["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid" />**hi**'


def test_skip_at_markdown_context() -> None:
    from nonebot_plugin_larkutils.qq_at_markdown import _message_to_markdown, skip_at_markdown

    message = _mention_message()
    with skip_at_markdown():
        assert _message_to_markdown(message) is None
    # token 已复位，上下文外仍然转换
    assert _message_to_markdown(message) is not None


def test_exporter_registered() -> None:
    from nonebot_plugin_alconna.uniseg.adapters import alter_get_exporter
    from nonebot_plugin_larkutils.qq_at_markdown import QQAtMarkdownExporter

    assert isinstance(alter_get_exporter("QQ"), QQAtMarkdownExporter)


@pytest.mark.asyncio
async def test_exporter_converts_group_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_alconna import Target
    from nonebot_plugin_alconna.uniseg.adapters.qq.exporter import QQMessageExporter
    from nonebot_plugin_larkutils.qq_at_markdown import QQAtMarkdownExporter

    base_send_to = AsyncMock(return_value=None)
    monkeypatch.setattr(QQMessageExporter, "send_to", base_send_to)

    exporter = QQAtMarkdownExporter()
    message = _mention_message()
    await exporter.send_to(Target.group("group_openid", adapter="QQ"), object(), message)

    sent_message = base_send_to.call_args.args[2]
    assert sent_message["mention_user"] == []
    assert '<qqbot-at-user id="member_openid" />' in sent_message["markdown"][0].data["markdown"].content


@pytest.mark.asyncio
async def test_exporter_keeps_private_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2C 单聊不支持 <qqbot-at-user>，不应改写为 markdown。"""
    from nonebot_plugin_alconna import Target
    from nonebot_plugin_alconna.uniseg.adapters.qq.exporter import QQMessageExporter
    from nonebot_plugin_larkutils.qq_at_markdown import QQAtMarkdownExporter

    base_send_to = AsyncMock(return_value=None)
    monkeypatch.setattr(QQMessageExporter, "send_to", base_send_to)

    exporter = QQAtMarkdownExporter()
    message = _mention_message()
    await exporter.send_to(Target.user("user_openid", adapter="QQ"), object(), message)

    sent_message = base_send_to.call_args.args[2]
    assert sent_message is message
    assert sent_message["mention_user"] != []


@pytest.mark.asyncio
async def test_at_sender_is_sent_as_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """matcher.send(..., at_sender=True) 最终发出的消息应是 markdown。"""
    from unittest.mock import MagicMock

    from nonebot_plugin_alconna import Target, UniMessage
    from nonebot_plugin_alconna.uniseg.adapters.qq.exporter import QQMessageExporter

    base_send_to = AsyncMock(return_value=None)
    monkeypatch.setattr(QQMessageExporter, "send_to", base_send_to)

    bot = MagicMock()
    bot.adapter.get_name.return_value = "QQ"
    await UniMessage().text("hello").send(
        target=Target.group("group_openid", adapter="QQ"),
        bot=bot,
        at_sender="member_openid",
    )

    sent_message = base_send_to.call_args.args[2]
    assert sent_message["mention_user"] == []
    assert sent_message["markdown"][0].data["markdown"].content == '<qqbot-at-user id="member_openid" />hello'


@pytest.mark.asyncio
async def test_panel_qq_sends_markdown_with_at(monkeypatch: pytest.MonkeyPatch) -> None:
    """/panel 的图片消息在 QQ 官方下改为 markdown 图片 + at。"""
    from unittest.mock import MagicMock

    import nonebot_plugin_larkuser.matchers.panel as panel

    class FakeQQBot:
        pass

    monkeypatch.setattr(panel, "QQBot", FakeQQBot)

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
    monkeypatch.setattr(panel, "render_template", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(panel, "create_image_markdown", AsyncMock(return_value="![panel](qqbot-media://panel)"))

    class FakeLang:
        async def text(self, key: str, _user_id: str, *_args: object) -> str:
            return key

    monkeypatch.setattr(panel, "lang", FakeLang())

    sent: list[str] = []

    class FakeUniMessage:
        def style(self, content: str, _style: str) -> "FakeUniMessage":
            self.content = content
            return self

        async def send(self, **_: object) -> None:
            sent.append(self.content)

    monkeypatch.setattr(panel, "UniMessage", FakeUniMessage)

    event = MagicMock()
    event.get_user_id.return_value = "member_openid"
    matcher = MagicMock()
    matcher.finish = AsyncMock()
    await panel.get_user_info(matcher, FakeQQBot(), event, "10")

    assert sent == ['<qqbot-at-user id="member_openid" />![panel](qqbot-media://panel)']
    matcher.finish.assert_awaited_once()
