from nonebot import logger
from nonebot_plugin_alconna import UniMessage, Alconna, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template, generate_render_keys
import httpx

matcher = on_alconna(Alconna("epic-free"), aliases={"epic"})
lang = LangHelper()


@matcher.handle()
async def _(user_id: str = get_user_id()) -> None:
    url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=zh-CN&country=CN&allowCountries=CN"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    logger.info("获取 Epic 免费游戏数据成功，正在渲染模版。")
    await UniMessage().image(
        raw=await render_template(
            "epic_free.html.jinja",
            await lang.text("title", user_id),
            user_id,
            {"result": data},
            await generate_render_keys(
                lang,
                user_id,
                [
                    "free_now",
                    "coming_soon",
                    "remaining",
                ],
                "template",
            ),
        )
    ).send()
    await matcher.finish()
