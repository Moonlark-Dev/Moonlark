"""chatterbox 排行榜的 QQ 适配器回归测试。

覆盖：
1. `/chatterbox` 不再被 `chat` 指令的命令前缀匹配误触发；
2. QQ 排行榜按钮指向其它时间段/统计范围/本人排名，且都是可解析的完整指令；
3. QQ 官方在排行榜图片之后追加一条带按钮的 markdown。
"""

from collections.abc import Iterable
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def patched_lang_and_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 LangHelper.text（避免读语言数据库）并固定命令前缀"""
    from nonebot_plugin_larkutils.command import config as command_config

    monkeypatch.setattr(command_config, "command_start", ["/"])

    from nonebot_plugin_chatterbox_ranking.lang import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


def _ob11_group_event(text: str):
    from nonebot.adapters.onebot.v11.event import GroupMessageEvent, Sender

    return GroupMessageEvent(
        time=1700000000,
        self_id=123,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        group_id=701257458,
        user_id=10001,
        raw_message=text,
        font=0,
        sender=Sender(user_id=10001, nickname="tester"),
        message=[{"type": "text", "data": {"text": text}}],
    )


async def _chat_command_matches(text: str) -> bool:
    """按 nonebot 处理事件的方式先跑命令前缀树，再判断 chat 响应器的规则"""
    from nonebot.rule import TrieRule
    from nonebot_plugin_chat.matcher.chat import chat

    bot, event, state = MagicMock(), _ob11_group_event(text), {}
    TrieRule.get_value(bot, event, state)
    return bool(await chat.rule(bot, event, state))


def _without_command_prefix(text: str, prefixes: Iterable[str]) -> str:
    """命令注册了前缀（ALCONNA_USE_COMMAND_START）时按钮文本自带前缀，否则解析前去掉"""
    if any(prefixes):
        return text
    from nonebot_plugin_larkutils.command import get_command_prefix

    return text.removeprefix(get_command_prefix())


@pytest.mark.asyncio
async def test_chatterbox_does_not_trigger_chat_command() -> None:
    """`/chatterbox` 会被命令前缀树解析成 `/chat` + `terbox`，必须不再命中 chat"""
    assert await _chat_command_matches("/chatterbox") is False
    assert await _chat_command_matches("/chatterbox 7d") is False
    assert await _chat_command_matches("/chatxxx") is False


@pytest.mark.asyncio
async def test_chat_command_still_matches_its_own_args() -> None:
    """限制空白符之后，`/chat` 与带参数的 `/chat xxx` 仍然可用"""
    assert await _chat_command_matches("/chat") is True
    assert await _chat_command_matches("/chat switch") is True


@pytest.mark.asyncio
async def test_rank_buttons_point_to_other_rankings() -> None:
    """群榜的键盘：三个时间段 + 切换到全局榜 + 我的排名"""
    from nonebot_plugin_chatterbox_ranking.__main__ import build_rank_buttons

    buttons = await build_rank_buttons("10", "7d", global_flag=False)
    assert [str(button.label) for button in buttons] == [
        "text::button.span_total",
        "text::button.span_7d",
        "text::button.span_1d",
        "text::button.scope_global",
        "text::button.me",
    ]
    assert [button.text for button in buttons] == [
        "/chatterbox total",
        "/chatterbox 7d",
        "/chatterbox 1d",
        "/chatterbox 7d --global",
        "/chatterbox 7d me",
    ]


@pytest.mark.asyncio
async def test_rank_buttons_keep_global_scope() -> None:
    """全局榜的键盘：时间段与「我的排名」保持全局，统计范围按钮切回本群"""
    from nonebot_plugin_chatterbox_ranking.__main__ import build_rank_buttons

    buttons = await build_rank_buttons("10", "total", global_flag=True)
    assert [button.text for button in buttons] == [
        "/chatterbox total --global",
        "/chatterbox 7d --global",
        "/chatterbox 1d --global",
        "/chatterbox total",
        "/chatterbox total me --global",
    ]
    assert str(buttons[3].label) == "text::button.scope_group"


@pytest.mark.asyncio
async def test_rank_buttons_are_parseable_commands() -> None:
    """按钮文本必须能被 chatterbox 解析，且指向预期的榜单"""
    from nonebot_plugin_chatterbox_ranking.__main__ import build_rank_buttons, chatterbox

    command = chatterbox.command()
    for span, global_flag in (("total", False), ("7d", True), ("1d", False)):
        buttons = await build_rank_buttons("10", span, global_flag)
        parsed = [command.parse(_without_command_prefix(button.text, command.prefixes)) for button in buttons]
        assert all(result.matched for result in parsed)
        assert [result.all_matched_args["span"] for result in parsed] == ["total", "7d", "1d", span, span]
        assert [bool(result.find("global")) for result in parsed] == [global_flag] * 3 + [
            not global_flag,
            global_flag,
        ]
        assert parsed[4].all_matched_args["user_id_arg"] == "me"


@pytest.mark.asyncio
async def test_send_rank_with_buttons_sends_image_then_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方：先发排行榜图片，再发一条带跳转按钮的 markdown"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Image, Keyboard, Text, UniMessage
    from nonebot_plugin_chatterbox_ranking.__main__ import send_rank_with_buttons

    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> MagicMock:
        sent.append(self)
        return MagicMock()

    monkeypatch.setattr(UniMessage, "send", fake_send)

    await send_rank_with_buttons(MagicMock(spec=QQBot), MagicMock(), "10", "7d", global_flag=False, image=b"png-bytes")

    assert len(sent) == 2
    image = next(seg for seg in sent[0] if isinstance(seg, Image))
    assert image.raw == b"png-bytes"

    text = next(seg for seg in sent[1] if isinstance(seg, Text))
    assert text.text == "text::button.tip"
    assert any("markdown" in styles for styles in text.styles.values())

    keyboard = next(seg for seg in sent[1] if isinstance(seg, Keyboard))
    assert keyboard.row == 3
    assert [button.text for button in keyboard.children] == [
        "/chatterbox total",
        "/chatterbox 7d",
        "/chatterbox 1d",
        "/chatterbox 7d --global",
        "/chatterbox 7d me",
    ]
