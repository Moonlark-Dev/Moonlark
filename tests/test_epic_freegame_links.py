"""nonebot_plugin_epic_freegame 的链接展示回归测试。

背景：/epic-free 原先只发送一张渲染图，图里的游戏名既不可点击、商店链接也没法复制。
现在 QQ 官方机器人改发 markdown（标题本身就是可点击的商店链接，下面再附一行裸链接
方便复制），其余平台在图片之外补一段纯文本链接列表。这里锁住这两条路径，以及
商店链接的解析回退逻辑。
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

_LANG_FILE = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "epic_freegame.yaml"
_STORE_BASE = "https://store.epicgames.com/zh-CN/p/"
_FREE_NOW_URL = f"{_STORE_BASE}out-of-sight-b96ca8"
_COMING_SOON_URL = f"{_STORE_BASE}bad-cheese-4256d9"


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


def _free_offer(start: str, end: str) -> dict[str, Any]:
    return {
        "promotionalOffers": [
            {
                "startDate": start,
                "endDate": end,
                "discountSetting": {"discountType": "PERCENTAGE", "discountPercentage": 0},
            }
        ]
    }


def _game(
    title: str,
    *,
    free_now: bool,
    slug: str | None = None,
    product_slug: str | None = None,
    price: str = "¥53.00",
    game_id: str = "game-id",
) -> dict[str, Any]:
    return {
        "id": game_id,
        "title": title,
        "description": f"{title} 的描述",
        "productSlug": product_slug,
        "urlSlug": "url-slug",
        "offerMappings": [{"pageSlug": slug, "pageType": "productHome"}] if slug else None,
        "catalogNs": {"mappings": [{"pageSlug": slug, "pageType": "productHome"}] if slug else []},
        "keyImages": [{"type": "OfferImageTall", "url": "https://cdn.example/tall.jpg"}],
        "price": {"totalPrice": {"fmtPrice": {"originalPrice": price}}},
        "promotions": {
            "promotionalOffers": (
                [_free_offer("2026-10-08T15:00:00.000Z", "2026-10-15T15:00:00.000Z")] if free_now else []
            ),
            "upcomingPromotionalOffers": (
                [] if free_now else [_free_offer("2026-10-18T15:00:00.000Z", "2026-10-22T15:00:00.000Z")]
            ),
        },
    }


def _payload(*games: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"Catalog": {"searchStore": {"elements": list(games)}}}}


def _normalized() -> list[dict[str, Any]]:
    """与 collect_free_games 输出同构、但时间固定的数据，供文案测试使用"""
    return [
        {
            "id": "1",
            "title": "虎视眈眈 (Out of Sight)",
            "description": "",
            "url": _FREE_NOW_URL,
            "image": None,
            "original_price": "¥53.00",
            "free_now": True,
            "countdown_date": None,
        },
        {
            "id": "2",
            "title": "Bad Cheese",
            "description": "",
            "url": _COMING_SOON_URL,
            "image": None,
            "original_price": "¥40.00",
            "free_now": False,
            "countdown_date": None,
        },
    ]


@pytest.fixture
def epic_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """按真实 epic_freegame.yaml 渲染 LangHelper.text，避免依赖数据库里的语言文本

    注意：插件导入必须在 fixture 内部进行（collection 阶段 nonebot 尚未初始化）。"""
    import nonebot_plugin_epic_freegame.__main__ as module
    from nonebot_plugin_larklang.__main__ import LangHelper, remove_trailing_blank_lines

    templates = _flatten(yaml.safe_load(_LANG_FILE.read_text(encoding="utf-8")))

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *args: object) -> str:
        return remove_trailing_blank_lines(templates[key].format(*args, __prefix__="/"))

    monkeypatch.setattr(LangHelper, "text", fake_text)
    return module


def test_get_store_url_prefers_product_slug() -> None:
    """有 productSlug 时直接用它，并去掉捆绑包特有的 /home 后缀"""
    from nonebot_plugin_epic_freegame.utils import get_store_url

    assert get_store_url({"productSlug": "ghostrunner-2"}) == f"{_STORE_BASE}ghostrunner-2"
    assert get_store_url({"productSlug": "some-bundle/home"}) == f"{_STORE_BASE}some-bundle"


def test_get_store_url_falls_back_to_page_slug() -> None:
    """没有 productSlug 的新上架游戏只有 pageSlug，必须回退到它（否则链接缺失）"""
    from nonebot_plugin_epic_freegame.utils import get_store_url

    assert get_store_url({"productSlug": None, "offerMappings": [{"pageSlug": "bad-cheese-4256d9"}]}) == (
        f"{_STORE_BASE}bad-cheese-4256d9"
    )
    nested = {"catalogNs": {"mappings": [{"page": {"pageSlug": "nested-slug"}}]}}
    assert get_store_url(nested) == f"{_STORE_BASE}nested-slug"
    assert get_store_url({"urlSlug": "fallback-slug"}) == f"{_STORE_BASE}fallback-slug"


def test_get_store_url_without_any_slug() -> None:
    """完全没有 slug 时返回 None，模板与文案都不应该拼出半截链接"""
    from nonebot_plugin_epic_freegame.utils import get_store_url

    assert get_store_url({"productSlug": None, "offerMappings": None, "catalogNs": None}) is None
    assert get_store_url({"productSlug": None, "offerMappings": [], "catalogNs": {"mappings": []}}) is None


def test_collect_free_games_keeps_free_promotions_only() -> None:
    """只保留 0 折（当前免费或即将免费）的条目，打折促销与无促销条目都要过滤掉"""
    from nonebot_plugin_epic_freegame.utils import collect_free_games

    discounted = _game("打折中", free_now=False, slug="discounted")
    discounted["promotions"] = {
        "promotionalOffers": [],
        "upcomingPromotionalOffers": [
            {
                "promotionalOffers": [
                    {
                        "startDate": "2026-10-15T15:00:00.000Z",
                        "endDate": "2026-10-22T15:00:00.000Z",
                        "discountSetting": {"discountType": "PERCENTAGE", "discountPercentage": 55},
                    }
                ]
            }
        ],
    }
    no_promotion = _game("没有活动", free_now=True, slug="no-promotion")
    no_promotion["promotions"] = None

    games = collect_free_games(
        _payload(
            _game("虎视眈眈 (Out of Sight)", free_now=True, slug="out-of-sight-b96ca8"),
            _game("Bad Cheese", free_now=False, slug="bad-cheese-4256d9", price="¥40.00"),
            discounted,
            no_promotion,
        )
    )

    assert [game["title"] for game in games] == ["虎视眈眈 (Out of Sight)", "Bad Cheese"]
    assert [game["free_now"] for game in games] == [True, False]
    assert games[0]["url"] == _FREE_NOW_URL
    assert games[0]["original_price"] == "¥53.00"
    # 当前免费看结束时间，即将免费看开始时间
    assert games[0]["countdown_date"] == "2026-10-15T15:00:00.000Z"
    assert games[1]["countdown_date"] == "2026-10-18T15:00:00.000Z"


def test_collect_free_games_tolerates_broken_payload() -> None:
    """接口结构变化时返回空列表，而不是抛异常让整个指令失败"""
    from nonebot_plugin_epic_freegame.utils import collect_free_games

    assert collect_free_games({}) == []
    assert collect_free_games({"data": {"Catalog": None}}) == []


def test_format_remaining_time() -> None:
    """倒计时格式与图片模板保持一致（XdYh），已过期或无法解析时不显示"""
    from nonebot_plugin_epic_freegame.utils import format_remaining_time

    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    assert format_remaining_time("2026-10-15T15:00:00.000Z", now) == "3d3h"
    assert format_remaining_time("2026-10-11T15:00:00.000Z", now) is None
    assert format_remaining_time("not-a-date", now) is None
    assert format_remaining_time(None, now) is None


@pytest.mark.asyncio
async def test_build_qq_markdown_has_clickable_and_copyable_links(epic_env: Any) -> None:
    """QQ markdown：标题是链接（可点击），下面另起一行裸链接（可复制）"""
    markdown = await epic_env.build_qq_markdown(_normalized(), "10")

    assert f"- [虎视眈眈 (Out of Sight)]({_FREE_NOW_URL})" in markdown
    assert f"- [Bad Cheese]({_COMING_SOON_URL})" in markdown
    # 每个链接出现两次：一次是 markdown 链接，一次是便于复制的裸链接
    assert markdown.count(_FREE_NOW_URL) == 2
    assert markdown.count(_COMING_SOON_URL) == 2
    assert "**当前免费**" in markdown
    assert "**即将免费**" in markdown
    assert "原价 ¥53.00" in markdown
    # 当前免费排在即将免费之前
    assert markdown.index("**当前免费**") < markdown.index("**即将免费**")


@pytest.mark.asyncio
async def test_build_qq_markdown_without_games(epic_env: Any) -> None:
    """没有免费游戏时给出文案，而不是一张空白图片"""
    assert await epic_env.build_qq_markdown([], "10") == "当前没有可以领取的 Epic 免费游戏，稍后再来看看吧。"


@pytest.mark.asyncio
async def test_build_qq_markdown_without_url(epic_env: Any) -> None:
    """解析不出链接的条目退化成纯标题，不产生空的 markdown 链接"""
    game = dict(_normalized()[0], url=None)
    markdown = await epic_env.build_qq_markdown([game], "10")

    assert "- 虎视眈眈 (Out of Sight)" in markdown
    assert "[" not in markdown


@pytest.mark.asyncio
async def test_build_plain_links_lists_copyable_urls(epic_env: Any) -> None:
    """非 QQ 平台：链接单独占一行，方便复制"""
    plain = await epic_env.build_plain_links(_normalized(), "10")

    assert f"【当前免费】\n虎视眈眈 (Out of Sight)\n{_FREE_NOW_URL}" in plain
    assert f"【即将免费】\nBad Cheese\n{_COMING_SOON_URL}" in plain
    # 纯文本里不能出现 markdown 链接语法，否则 OneBot 客户端会原样显示
    assert "](" not in plain


@pytest.mark.asyncio
async def test_handle_epic_free_qq_sends_markdown(epic_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人：发送 markdown 消息（不渲染图片），并单独结束处理器"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Text, UniMessage

    module = epic_env
    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    finish = AsyncMock()
    monkeypatch.setattr(module, "fetch_free_games", AsyncMock(return_value=_normalized()))
    monkeypatch.setattr(UniMessage, "send", fake_send)
    monkeypatch.setattr(module.matcher, "finish", finish)

    await module.handle_epic_free(bot=MagicMock(spec=QQBot), user_id="10")

    assert len(sent) == 1
    text = next(seg for seg in sent[0] if isinstance(seg, Text))
    assert any("markdown" in styles for styles in text.styles.values())
    assert f"[虎视眈眈 (Out of Sight)]({_FREE_NOW_URL})" in text.text
    finish.assert_awaited()


@pytest.mark.asyncio
async def test_handle_epic_free_other_adapter_sends_image_with_links(
    epic_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """其余平台：图片 + 纯文本链接列表，链接可以复制"""
    from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

    module = epic_env
    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    finish = AsyncMock()
    render = AsyncMock(return_value=b"webp-bytes")
    monkeypatch.setattr(module, "fetch_free_games", AsyncMock(return_value=_normalized()))
    monkeypatch.setattr(module, "render_template", render)
    monkeypatch.setattr(UniMessage, "send", fake_send)
    monkeypatch.setattr(module.matcher, "finish", finish)

    await module.handle_epic_free(bot=MagicMock(), user_id="10")

    assert len(sent) == 1
    assert any(isinstance(seg, Image) for seg in sent[0])
    text = next(seg for seg in sent[0] if isinstance(seg, Text))
    assert _FREE_NOW_URL in text.text
    assert _COMING_SOON_URL in text.text
    # generate_render_keys 的前缀必须带点号，否则图片里会渲染出 [缺失: ...] 占位符
    assert render.await_args.kwargs["keys"] == {
        "free_now": "当前免费",
        "coming_soon": "即将免费",
        "remaining": "剩余",
        "store_link": "商店链接",
    }
    finish.assert_awaited()
