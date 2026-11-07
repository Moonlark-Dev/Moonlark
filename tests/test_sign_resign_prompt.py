from types import SimpleNamespace
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
    monkeypatch.setattr("nonebot_plugin_sign.__main__.has_new_update", AsyncMock(return_value=False))
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
    monkeypatch.setattr("nonebot_plugin_sign.__main__.has_new_update", AsyncMock(return_value=False))
    monkeypatch.setattr(config, "command_start", ["/"])
    buttons = await handler.build_button()

    assert len(buttons) == 3
    assert str(buttons[-1].label) == "text::button.email"
    assert buttons[-1].text == "/email"


@pytest.mark.asyncio
async def test_build_button_adds_updates_when_new_update(monkeypatch: pytest.MonkeyPatch) -> None:
    """有未阅读的更新公告时键盘应额外包含 查看更新 按钮并指向 bc 指令"""
    from nonebot_plugin_sign.__main__ import config

    handler = _make_handler(bot=MagicMock())
    monkeypatch.setattr("nonebot_plugin_sign.__main__.get_unread_email_count", AsyncMock(return_value=0))
    monkeypatch.setattr("nonebot_plugin_sign.__main__.has_new_update", AsyncMock(return_value=True))
    monkeypatch.setattr(config, "command_start", ["/"])
    buttons = await handler.build_button()

    assert len(buttons) == 3
    assert str(buttons[-1].label) == "text::button.updates"
    assert buttons[-1].text == "/bc"


@pytest.mark.asyncio
async def test_build_button_adds_setu_original_when_header_from_setu(monkeypatch: pytest.MonkeyPatch) -> None:
    """头图来自 setu 时键盘应额外包含「查看原图」按钮，指向 setu-g 指令"""
    from nonebot_plugin_sign.__main__ import config

    handler = _make_handler(bot=MagicMock())
    handler._setu_image_id = "123_0"  # ruff: ignore[private-member-access]
    monkeypatch.setattr("nonebot_plugin_sign.__main__.get_unread_email_count", AsyncMock(return_value=0))
    monkeypatch.setattr("nonebot_plugin_sign.__main__.has_new_update", AsyncMock(return_value=False))
    monkeypatch.setattr(config, "command_start", ["#"])

    buttons = await handler.build_button()

    assert [str(button.label) for button in buttons] == [
        "text::button.invite",
        "text::button.setu_original",
        "text::button.jrrp",
    ]
    assert buttons[1].text == "#setu-g 123_0"


@pytest.mark.parametrize("ext", ["jpg", "png"])
@pytest.mark.asyncio
async def test_render_result_remembers_setu_image_id(monkeypatch: pytest.MonkeyPatch, ext: str) -> None:
    """用 setu 横版图做头图时记录缓存 ID，供「查看原图」按钮使用"""
    from nonebot_plugin_larksetu.models import ImageData
    from nonebot_plugin_sign.__main__ import SignHandler

    data = ImageData(
        pid=123,
        p=0,
        uid=1,
        title="title",
        author="author",
        r18=False,
        width=1920,
        height=1080,
        tags=[],
        ext=ext,
        aiType=0,
        uploadDate=0,
        urls={"original": "https://example.com/image.jpg"},
    )
    render_template = AsyncMock(return_value=b"card")
    monkeypatch.setattr(
        "nonebot_plugin_sign.__main__.get_landscape_image",
        AsyncMock(return_value={"data": data, "image": b"background"}),
    )
    monkeypatch.setattr("nonebot_plugin_sign.__main__._get_hitokoto", AsyncMock(return_value="hitokoto"))
    monkeypatch.setattr("nonebot_plugin_sign.__main__._get_luck", AsyncMock(return_value="a"))
    monkeypatch.setattr(
        "nonebot_plugin_sign.__main__.get_user",
        AsyncMock(return_value=SimpleNamespace(nickname="nick", avatar=None)),
    )
    monkeypatch.setattr("nonebot_plugin_sign.__main__.render_template", render_template)

    handler = SignHandler(user_id="10", bot=MagicMock(), event=MagicMock(), matcher=MagicMock())
    handler._result = {
        "sign_days": 3,
        "rank": 1,
        "exp": {"text": "", "origin": 0, "now": 1, "add": 1},
        "vim": {"text": "", "add": 1, "origin": 0, "now": 1},
        "fav": {"text": "", "add": 1, "now": 1, "origin": 0},
        "ticket_gained": 0,
    }
    handler.send_card = AsyncMock()  # type: ignore[method-assign]

    await handler.render_result()

    assert handler._setu_image_id == "123_0"  # ruff: ignore[private-member-access]
    background_url = handler._bg_kwargs["background_url"]  # ruff: ignore[private-member-access]
    assert background_url.startswith(f"data:image/{'png' if ext == 'png' else 'jpeg'};base64,")
    handler.send_card.assert_awaited_once_with(b"card")


def _make_markdown_handler(monkeypatch: pytest.MonkeyPatch, event: MagicMock) -> tuple[object, list]:
    """构造可调用 format_markdown 的 SignHandler，隔离图片生成/邮件查询/消息发送"""
    from nonebot_plugin_alconna import UniMessage

    from nonebot_plugin_sign.__main__ import SignHandler

    monkeypatch.setattr("nonebot_plugin_sign.__main__.create_image_markdown", AsyncMock(return_value="![签到卡片]"))
    monkeypatch.setattr("nonebot_plugin_sign.__main__.get_unread_email_count", AsyncMock(return_value=0))

    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    monkeypatch.setattr(UniMessage, "send", fake_send)

    matcher = MagicMock()
    matcher.finish = AsyncMock()
    handler = SignHandler(user_id="10", bot=MagicMock(), event=event, matcher=matcher)
    handler._result = {"sign_days": 1}  # ruff: ignore[private-member-access]
    return handler, sent


@pytest.mark.asyncio
async def test_format_markdown_c2c_skips_at_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2C 单聊消息不支持 qqbot-at-user 提及，签到卡片应跳过 @ 前缀"""
    from nonebot.adapters.qq.event import C2CMessageCreateEvent
    from nonebot_plugin_alconna import Text

    handler, sent = _make_markdown_handler(monkeypatch, event=MagicMock(spec=C2CMessageCreateEvent))

    await handler.format_markdown(b"image")

    text = next(seg for seg in sent[0] if isinstance(seg, Text))
    assert text.text == "![签到卡片]"
    handler.matcher.finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_format_markdown_group_chat_prepends_at_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """群聊消息应保留 qqbot-at-user @ 前缀"""
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
    from nonebot_plugin_alconna import Text

    event = MagicMock(spec=GroupAtMessageCreateEvent)
    event.get_user_id.return_value = "member_openid_1"
    handler, sent = _make_markdown_handler(monkeypatch, event=event)

    await handler.format_markdown(b"image")

    text = next(seg for seg in sent[0] if isinstance(seg, Text))
    assert text.text == '<qqbot-at-user id="member_openid_1" />![签到卡片]'
    handler.matcher.finish.assert_awaited_once()
