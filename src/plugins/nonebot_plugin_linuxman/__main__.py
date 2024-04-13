from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id
import httpx
from .config import config
from nonebot_plugin_htmlrender import text_to_pic
from nonebot_plugin_alconna import on_alconna, Args, Alconna, Arparma, Match
from nonebot_plugin_alconna.uniseg import UniMessage

lang = LangHelper()
man = on_alconna(
    Alconna(
        "man",
        Args["name", str],
        Args["page", int, 1]
    )
)


@man.handle()
async def _(name: str, page: int, user_id: str = get_user_id()) -> None:
    p = page
    async with httpx.AsyncClient(base_url=config.linuxman_url) as client:
        response = await client.get(f"/{name}.{p}.txt")
    if response.status_code == 404:
        await lang.finish("man.not_found", user_id, name, p)
    await man.finish(UniMessage().image(raw=await text_to_pic(response.text)), reply_message=True)
    
