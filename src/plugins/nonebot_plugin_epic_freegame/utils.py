"""Epic 免费游戏数据的解析工具。

这里的函数只做数据清洗，不依赖 NoneBot，方便单独测试：模板渲染与消息文案
都基于 ``collect_free_games`` 产出的统一结构，避免在 Jinja 模板里重复解析
``productSlug`` / ``offerMappings`` 等易变的接口字段。
"""

from datetime import datetime, timezone
import re
from typing import Any

EPIC_API_URL = (
    "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
    "?locale=zh-CN&country=CN&allowCountries=CN"
)
# 商店页面统一使用接口请求的 zh-CN 地区，保证与文案、价格货币一致
STORE_BASE_URL = "https://store.epicgames.com/zh-CN/p/"
# QQ markdown 海报的显示宽度；Epic 原图是 2560x1440，按这个宽度等比缩小
MARKDOWN_IMAGE_MAX_WIDTH = 760
# Epic 的图片地址常带 2560x1440 这样的尺寸，用来还原海报的宽高比
_IMAGE_SIZE_PATTERN = re.compile(r"(\d{3,4})x(\d{3,4})")


def _first_page_slug(mappings: Any) -> str | None:
    """从 ``offerMappings`` / ``catalogNs.mappings`` 中取出第一个页面 slug"""
    if not isinstance(mappings, list):
        return None
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        page = mapping.get("page")
        for slug in (mapping.get("pageSlug"), page.get("pageSlug") if isinstance(page, dict) else None):
            if slug:
                return str(slug)
    return None


def get_store_url(game: dict[str, Any]) -> str | None:
    """解析游戏在 Epic 商店的页面地址。

    Epic 接口并不总是给出 ``productSlug``：新上架游戏与捆绑包经常只有
    ``offerMappings`` / ``catalogNs.mappings`` 里的 ``pageSlug``，因此依次回退；
    捆绑包的 slug 可能带 ``/home`` 后缀，需要去掉才能指向商品页。
    """
    catalog_ns = game.get("catalogNs")
    slug = (
        game.get("productSlug")
        or _first_page_slug(game.get("offerMappings"))
        or _first_page_slug(catalog_ns.get("mappings") if isinstance(catalog_ns, dict) else None)
        or game.get("urlSlug")
    )
    if not slug:
        return None
    return f"{STORE_BASE_URL}{str(slug).removesuffix('/home')}"


def build_markdown_image(url: str, alt: str, max_width: int = MARKDOWN_IMAGE_MAX_WIDTH) -> str:
    """生成 QQ markdown 的图片代码。

    Epic 的图片地址里通常带原始尺寸（如 ``..._2560x1440-....jpg``），用它等比
    缩放到合适大小后写成 ``![alt #宽px #高px](url)``（QQ 的尺寸语法）；拿不到
    尺寸时退回普通 markdown 图片，交给 QQ 自行缩放。宽高都不超过 max_width，
    这样即使横版海报缺失、退回竖版封面也不会得到一张过高的图。
    """
    match = _IMAGE_SIZE_PATTERN.search(url)
    if match is None:
        return f"![{alt}]({url})"
    width, height = int(match.group(1)), int(match.group(2))
    scale = min(max_width / width, max_width / height, 1.0)
    return f"![{alt} #{round(width * scale)}px #{round(height * scale)}px]({url})"


def _is_free_offer(offer_group: Any) -> bool:
    """判断一个促销分组是否是 0 折（也就是免费）活动"""
    if not isinstance(offer_group, dict):
        return False
    offers = offer_group.get("promotionalOffers")
    if not isinstance(offers, list) or not offers or not isinstance(offers[0], dict):
        return False
    discount = offers[0].get("discountSetting")
    if not isinstance(discount, dict):
        return False
    return discount.get("discountType") == "PERCENTAGE" and discount.get("discountPercentage") == 0


def _first_free_offer(offer_groups: Any) -> dict[str, Any] | None:
    """在促销分组里找到第一个免费活动的具体 offer"""
    if not isinstance(offer_groups, list):
        return None
    for group in offer_groups:
        if _is_free_offer(group):
            return group["promotionalOffers"][0]
    return None


def _first_image(key_images: Any, *image_types: str) -> str | None:
    """按优先级取第一张可用图片。

    Epic 的免费条目通常同时给出竖版 ``OfferImageTall``（1200x1600）与横版
    ``OfferImageWide``（2560x1440）：图片模板的卡片是竖版位，QQ markdown 的海报
    则用横版，因此两者各取所需并互相兜底。
    """
    if not isinstance(key_images, list):
        return None
    for image_type in image_types:
        for image in key_images:
            if isinstance(image, dict) and image.get("type") == image_type and image.get("url"):
                return str(image["url"])
    return None


def _original_price(game: dict[str, Any]) -> str | None:
    price = game.get("price")
    if not isinstance(price, dict):
        return None
    total_price = price.get("totalPrice")
    if not isinstance(total_price, dict):
        return None
    fmt_price = total_price.get("fmtPrice")
    if not isinstance(fmt_price, dict):
        return None
    original = fmt_price.get("originalPrice")
    return str(original) if original else None


def collect_free_games(data: dict[str, Any]) -> list[dict[str, Any]]:
    """从接口返回的 JSON 中筛选出当前/即将免费的条目。

    返回的每一项都是模板与文案直接可用的结构；同一个游戏的多个促销分组里
    只要存在 0 折活动就算免费（当前的 0 折优先于即将到来的 0 折）。
    """
    games: list[dict[str, Any]] = []
    try:
        elements = data["data"]["Catalog"]["searchStore"]["elements"]
    except (KeyError, TypeError):
        return games
    if not isinstance(elements, list):
        return games
    for game in elements:
        if not isinstance(game, dict):
            continue
        promotions = game.get("promotions")
        if not isinstance(promotions, dict):
            continue
        offer = _first_free_offer(promotions.get("promotionalOffers"))
        free_now = offer is not None
        if offer is None:
            offer = _first_free_offer(promotions.get("upcomingPromotionalOffers"))
        if offer is None:
            continue
        key_images = game.get("keyImages")
        games.append(
            {
                "id": str(game.get("id") or game.get("title") or ""),
                "title": str(game.get("title") or ""),
                "description": str(game.get("description") or ""),
                "url": get_store_url(game),
                # 图片模板的卡片是竖版位，QQ markdown 的海报用横版
                "image": _first_image(key_images, "OfferImageTall", "OfferImageWide"),
                "wide_image": _first_image(key_images, "OfferImageWide", "OfferImageTall"),
                "original_price": _original_price(game),
                "free_now": free_now,
                # 当前免费显示距结束的倒计时，即将免费显示距开始的时间
                "countdown_date": offer.get("endDate") if free_now else offer.get("startDate"),
            }
        )
    return games


def parse_epic_datetime(value: Any) -> datetime | None:
    """解析接口返回的 ISO 8601 时间（形如 ``2026-10-15T15:00:00.000Z``）"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_remaining_time(value: Any, now: datetime | None = None) -> str | None:
    """把倒计时格式化成 ``3d12h`` 这样与图片模板一致的紧凑文本

    时间已过（或无法解析）时返回 ``None``，由调用方决定不显示倒计时。
    """
    target = parse_epic_datetime(value)
    if target is None:
        return None
    current = now or datetime.now(timezone.utc)
    time_diff = target - current
    if time_diff.total_seconds() <= 0:
        return None
    days = time_diff.days
    hours = time_diff.seconds // 3600
    return f"{days}d{hours}h"
