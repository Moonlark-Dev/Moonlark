import httpx
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, UniMessage, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import generate_render_keys, render_template

from .utils import EPIC_API_URL, collect_free_games, format_remaining_time

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
    """拼装一条游戏的附加信息：原价与剩余/开始时间"""
    parts = []
    if game["original_price"]:
        parts.append(await lang.text("meta.price", user_id, game["original_price"]))
    remaining = format_remaining_time(game["countdown_date"])
    if remaining:
        parts.append(await lang.text("meta.remaining" if game["free_now"] else "meta.upcoming", user_id, remaining))
    return " · ".join(parts)


async def build_qq_markdown(games: list[dict], user_id: str) -> str:
    """构建 QQ 官方机器人的 markdown 文案

    标题本身就是商店链接（点击可跳转），下面再附一行裸链接，方便长按复制。
    """
    if not games:
        return await lang.text("empty", user_id)
    lines = [await lang.text("markdown.title", user_id), ""]
    for free_now in (True, False):
        group = [game for game in games if game["free_now"] is free_now]
        if not group:
            continue
        lines.append(await lang.text("markdown.free_now" if free_now else "markdown.coming_soon", user_id))
        for game in group:
            if game["url"]:
                lines.append(await lang.text("markdown.item", user_id, game["title"], game["url"]))
            else:
                lines.append(await lang.text("markdown.item_plain", user_id, game["title"]))
            meta = await build_game_meta(game, user_id)
            if meta:
                lines.append(await lang.text("markdown.item_meta", user_id, meta))
            if game["url"]:
                lines.append(await lang.text("markdown.item_link", user_id, game["url"]))
        lines.append("")
    return "\n".join(lines).strip()


async def build_plain_links(games: list[dict], user_id: str) -> str:
    """非 QQ 平台：纯文本列出商店链接。

    这些适配器不支持 markdown，链接无法点击，所以把链接单独放一行方便复制。
    """
    blocks = []
    for free_now in (True, False):
        group = [game for game in games if game["free_now"] is free_now]
        if not group:
            continue
        lines = [await lang.text("plain.free_now" if free_now else "plain.coming_soon", user_id)]
        for game in group:
            if game["url"]:
                lines.append(await lang.text("plain.item", user_id, game["title"], game["url"]))
            else:
                lines.append(game["title"])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


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
        # QQ 官方机器人直接发 markdown：标题即商店链接，点击可跳转
        message = UniMessage().style(await build_qq_markdown(games, user_id), "markdown")
    else:
        logger.info("获取 Epic 免费游戏数据成功，正在渲染模版。")
        message = UniMessage().image(
            raw=await render_template(
                "epic_free.html.jinja",
                await lang.text("title", user_id),
                user_id,
                {"games": games},
                keys=await generate_render_keys(lang, user_id, TEMPLATE_KEYS, "template."),
            )
        )
        links = await build_plain_links(games, user_id)
        if links:
            message = message.text(f"\n{links}")
    await message.send()
    await matcher.finish()
