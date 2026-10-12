import httpx
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, UniMessage, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import generate_render_keys, render_template

from .utils import EPIC_API_URL, build_markdown_image, collect_free_games, format_remaining_time

matcher = on_alconna(Alconna("epic-free"), aliases={"epic"})
lang = LangHelper()

TEMPLATE_KEYS = ["free_now", "coming_soon", "remaining", "store_link"]


async def fetch_free_games() -> list[dict]:
    """拉取并解析 Epic 免费游戏数据"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(EPIC_API_URL)
        resp.raise_for_status()
        data = resp.json()
    return collect_free_games(data)


async def build_game_meta(game: dict, user_id: str) -> str:
    """当前免费条目的括号文案：原价与剩余时间"""
    parts = []
    if game["original_price"]:
        parts.append(await lang.text("meta.price", user_id, game["original_price"]))
    remaining = format_remaining_time(game["countdown_date"])
    if remaining:
        parts.append(await lang.text("meta.remaining", user_id, remaining))
    return " · ".join(parts)


async def build_qq_item_link(game: dict, user_id: str) -> str:
    """加粗的标题链接；没有商店链接时退化成纯标题"""
    if game["url"]:
        return await lang.text("markdown.item", user_id, game["title"], game["url"])
    return await lang.text("markdown.item_plain", user_id, game["title"])


async def build_qq_free_now_item(game: dict, user_id: str) -> list[str]:
    """当前免费条目：横版海报 + 加粗标题链接 + > 简介（原价 · 剩余）裸链接"""
    lines = []
    if game["wide_image"]:
        lines.append(build_markdown_image(game["wide_image"], game["title"]))
    lines.append(await build_qq_item_link(game, user_id))
    description = game["description"] or game["title"]
    url = game["url"] or ""
    meta = await build_game_meta(game, user_id)
    if meta:
        quote = await lang.text("markdown.quote", user_id, description, meta, url)
    else:
        quote = await lang.text("markdown.quote_no_meta", user_id, description, url)
    lines.append(quote.rstrip())
    return lines


async def build_qq_markdown(games: list[dict], user_id: str) -> str:
    """构建 QQ 官方机器人的 markdown 文案

    当前免费给完整卡片（横版海报 + 加粗标题链接 + 简介引用行），即将免费只列
    一行加粗标题链接；条目之间空一行。
    """
    if not games:
        return await lang.text("empty", user_id)
    blocks = [await lang.text("markdown.title", user_id)]
    free_now_games = [game for game in games if game["free_now"]]
    if free_now_games:
        items = ["\n".join(await build_qq_free_now_item(game, user_id)) for game in free_now_games]
        blocks.append("\n\n".join([await lang.text("markdown.free_now", user_id), *items]))
    coming_soon_games = [game for game in games if not game["free_now"]]
    if coming_soon_games:
        items = [await build_qq_item_link(game, user_id) for game in coming_soon_games]
        blocks.append("\n\n".join([await lang.text("markdown.coming_soon", user_id), *items]))
    return "\n\n".join(blocks)


async def build_plain_links(games: list[dict], user_id: str) -> str:
    """非 QQ 平台第二条消息：当前免费游戏的纯文本链接列表

    这些适配器不支持 markdown，链接无法点击，所以一个游戏两行、链接单独一行方便复制。
    """
    free_now_games = [game for game in games if game["free_now"]]
    if not free_now_games:
        return ""
    lines = [await lang.text("plain.free_now", user_id)]
    for game in free_now_games:
        if game["url"]:
            lines.append(await lang.text("plain.item", user_id, game["title"], game["url"]))
        else:
            lines.append(game["title"])
    return "\n".join(lines)


@matcher.handle()
async def handle_epic_free(bot: Bot, user_id: str = get_user_id()) -> None:
    try:
        games = await fetch_free_games()
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"获取 Epic 免费游戏数据失败：{error}")
        await lang.finish("failed", user_id)

    if not games:
        await lang.finish("empty", user_id)

    if isinstance(bot, QQBot):
        # QQ 官方机器人：一条 markdown（海报 + 可点击标题 + 可复制裸链接）
        await UniMessage().style(await build_qq_markdown(games, user_id), "markdown").send()
    else:
        # 其余平台：第一条发渲染图，第二条发当前免费游戏的链接列表
        logger.info("获取 Epic 免费游戏数据成功，正在渲染模版。")
        await UniMessage().image(
            raw=await render_template(
                "epic_free.html.jinja",
                await lang.text("title", user_id),
                user_id,
                {"games": games},
                keys=await generate_render_keys(lang, user_id, TEMPLATE_KEYS, "template."),
            )
        ).send()
        links = await build_plain_links(games, user_id)
        if links:
            await UniMessage().text(links).send()
    await matcher.finish()
