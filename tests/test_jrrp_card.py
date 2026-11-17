"""jrrp 人品卡（Pillow）的回归测试。

插画是按签到插件 ``nonebot_plugin_sign`` 的 a~f 六档运势裁的；两边分档一旦漂移，
同一分值就会出现「签到卡是大吉、人品卡是大凶」的错位，所以这里把边界和接线都钉住。
"""

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from PIL import Image

CARD_SIZE = (920, 580)
TIERS = ["a", "b", "c", "d", "e", "f"]

JRRP_TIERS = [
    "beyond_perfect",
    "perfect_luck",
    "almost_perfect",
    "great_day",
    "good_day",
    "fair_day",
    "average_day",
    "below_average",
    "poor_day",
    "bad_day",
    "terrible_luck",
]

FAKE_TEXTS = {
    "card.title": "MOONLARK · 今日人品",
    "card.unit": "/ 100",
    "card.unit_max": "MAX",
    "card.fortune.a": "大吉",
    "card.fortune.b": "吉",
    "card.fortune.c": "小吉",
    "card.fortune.d": "末吉",
    "card.fortune.e": "凶",
    "card.fortune.f": "大凶",
    "card.phrase.beyond_perfect": "{}！！突破天际！！！",
    "card.phrase.perfect_luck": "{}！100！100！！！",
    "card.phrase.almost_perfect": "{}！可惜不是 100",
    "card.phrase.great_day": "是不错的一天呢！",
    "card.phrase.good_day": "还行啦还行啦。",
    "card.phrase.fair_day": "平平稳稳，也挺好。",
    "card.phrase.average_day": "………………",
    "card.phrase.below_average": "…………………………………………",
    "card.phrase.poor_day": "呜哇——",
    "card.phrase.bad_day": "呜哇——（没错，是百分制）",
    "card.phrase.terrible_luck": "{}！0！0！！！",
}


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 jrrp 插件的 LangHelper.text，避免依赖数据库读取语言文本。"""
    from nonebot_plugin_jrrp.lang import lang

    async def fake_text(key: str, _user_id: str, *args: object, **_kwargs: object) -> str:
        if key.startswith("card.phrase."):
            return str(FAKE_TEXTS[key]).format(*args)
        return FAKE_TEXTS.get(key, f"text::{key}")

    monkeypatch.setattr(lang, "text", fake_text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (150, "a"),
        (101, "a"),
        (100, "a"),
        (81, "a"),
        (80, "b"),
        (61, "b"),
        (60, "c"),
        (41, "c"),
        (40, "d"),
        (21, "d"),
        (20, "e"),
        (1, "e"),
        (0, "f"),
    ],
)
def test_fortune_key_boundaries(value: int, expected: str) -> None:
    from nonebot_plugin_jrrp.card import get_fortune_key

    assert get_fortune_key(value) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [150, 100, 81, 80, 61, 60, 41, 40, 21, 20, 1, 0])
async def test_fortune_matches_sign_plugin(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    """人品卡的六档必须和签到插件完全一致。"""
    from nonebot_plugin_jrrp.card import get_fortune_key
    from nonebot_plugin_sign import __main__ as sign_main

    monkeypatch.setattr(sign_main, "get_luck_value", AsyncMock(return_value=value))
    assert await sign_main._get_luck("10") == get_fortune_key(value)


@pytest.mark.asyncio
async def test_render_luck_card_png() -> None:
    from nonebot_plugin_jrrp.card import render_luck_card

    data = await render_luck_card("10", 85)

    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(data)) as image:
        assert image.size == CARD_SIZE
        assert image.mode == "RGB"


@pytest.mark.asyncio
@pytest.mark.parametrize(("value", "tier"), [(90, "a"), (70, "b"), (50, "c"), (30, "d"), (10, "e"), (0, "f")])
async def test_every_tier_has_illustration(value: int, tier: str) -> None:
    from nonebot_plugin_jrrp.card import render_luck_card

    illustration = Path(__file__).resolve().parents[1] / "src" / "static" / "jrrp" / "moonlark" / f"{tier}.png"
    assert illustration.is_file(), f"缺少运势 {tier} 的插画"
    assert (await render_luck_card("10", value)).startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("value", "tier", "expected"),
    [
        (150, "beyond_perfect", "150！！突破天际！！！"),
        (100, "perfect_luck", "100！100！100！！！"),
        (99, "almost_perfect", "99！可惜不是 100"),
        (85, "great_day", "是不错的一天呢！"),
        (75, "good_day", "还行啦还行啦。"),
        (60, "fair_day", "平平稳稳，也挺好。"),
        (52, "average_day", "………………"),
        (25, "poor_day", "呜哇——"),
        (12, "bad_day", "呜哇——（没错，是百分制）"),
        (0, "terrible_luck", "0！0！0！！！"),
    ],
)
def test_card_phrase_values(value: int, tier: str, expected: str) -> None:
    """卡面上的句子直接写在 card.phrase.<tier> 里，代码只做 format，不改标点。"""
    lang_file = Path(__file__).resolve().parents[1] / "src" / "lang" / "zh_hans" / "jrrp.yaml"
    data = yaml.safe_load(lang_file.read_text(encoding="utf-8"))

    assert data["card"]["phrase"][tier].format(value) == expected


@pytest.mark.asyncio
async def test_render_fair_day_phrase() -> None:
    from nonebot_plugin_jrrp.card import render_luck_card

    # fair_day 原文没有人品值后面的句子，语言文件里给了完整兜底句
    assert (await render_luck_card("10", 60)).startswith(b"\x89PNG")


def test_wrap_phrase_breaks_after_comma() -> None:
    from nonebot_plugin_jrrp.card import _wrap_phrase

    lines = _wrap_phrase("今天幸运值拉满，想做的事就放心去做吧～", 26, 486)

    assert lines == ["今天幸运值拉满，", "想做的事就放心去做吧～"]


def test_card_language_keys_cover_all_tiers() -> None:
    lang_file = Path(__file__).resolve().parents[1] / "src" / "lang" / "zh_hans" / "jrrp.yaml"
    data = yaml.safe_load(lang_file.read_text(encoding="utf-8"))

    assert set(data["card"]["fortune"]) == set(TIERS)
    assert set(data["card"]["phrase"]) == set(JRRP_TIERS)


@pytest.mark.asyncio
async def test_build_jrrp_card_message_qq_uses_markdown_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage
    from nonebot_plugin_jrrp.__main__ import build_jrrp_card_message
    from nonebot_plugin_larkutils.command import config

    async def fake_upload(data: bytes, _bot: object) -> str:
        assert data == b"card-bytes"
        return "![人品卡 #920px #580px](qqbot-media://fake)"

    monkeypatch.setattr("nonebot_plugin_jrrp.__main__.create_image_markdown", fake_upload)
    monkeypatch.setattr(config, "command_start", ["/"])
    event = MagicMock(spec=GroupAtMessageCreateEvent)
    event.get_user_id.return_value = "MEMBER_OPENID"

    message = await build_jrrp_card_message(MagicMock(spec=QQBot), "10001", b"card-bytes", event)

    assert isinstance(message, UniMessage)
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == '<qqbot-at-user id="MEMBER_OPENID" />![人品卡 #920px #580px](qqbot-media://fake)'
    assert any("markdown" in styles for styles in text.styles.values())
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    assert [button.text for button in keyboard.children] == ["/jrrp r", "/jrrp rr", "/jrrp reroll"]


@pytest.mark.asyncio
async def test_build_jrrp_card_message_image_on_other_adapters() -> None:
    from nonebot_plugin_alconna.uniseg import Image
    from nonebot_plugin_jrrp.__main__ import build_jrrp_card_message

    message = await build_jrrp_card_message(MagicMock(), "10", b"card-bytes")

    image = next(seg for seg in message if isinstance(seg, Image))
    assert image.raw == b"card-bytes"


@pytest.mark.asyncio
async def test_try_render_luck_card_falls_back_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_jrrp import __main__ as module

    monkeypatch.setattr(module, "render_luck_card", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(module.logger, "exception", lambda *_args, **_kwargs: None)

    assert await module.try_render_luck_card("10", 85) is None
