import traceback
from .config import Config
from nonebot import get_plugin_config
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id, review_image
from nonebot_plugin_alconna import Option, Query, UniMsg, on_alconna, Args, Alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from .exception import AccessDenied
from .checker import check_url_protocol
from nonebot_plugin_htmlrender import get_new_page, md_to_pic
import asyncio

        

config = get_plugin_config(Config)
preview = on_alconna(
    Alconna(
        "preview",
        Args["url", str],
        Option("--wait|-w", Args["wait", int, 3])
    ),
    use_cmd_start=True,
    skip_for_unmatch=False,
    # auto_send_output=True
)
lang = LangHelper()

async def screenshot(url: str, wait: int) -> bytes:
    async with get_new_page() as page:
        await page.goto(url)
        await asyncio.sleep(wait)
        return await page.screenshot(
            type="jpeg",
            full_page=True
        )

@preview.handle()
async def _(url: str, msg: UniMsg, wait: Query[int] = Query("wait.wait"), user_id: str = get_user_id()) -> None:
    if not url:
        await lang.finish("preview.needarg", user_id)
    try:
        if not check_url_protocol(url):
            url = f"http://{url}"
    except AccessDenied:
        await lang.finish("preview.access_denied", user_id)
    try:
        pic = await screenshot(url, wait.result if wait.available else 3)
    except Exception:
        err = traceback.format_exc()
        await preview.finish(
            UniMessage().image(
                raw=await md_to_pic(
                    await lang.text(
                        "preview.failed", 
                        user_id,
                        err.split("\n")[-2],
                        err
                    ),
                    width=1000
                ),
                name="image.png"
            ),
            reply_message=True
        )
    if not (result := await review_image(pic))["compliance"]:
        await lang.finish("preview.not_compliance", user_id, result["message"])
    await UniMessage().image(raw=pic, name="image.jpg").send(reply_to=True)

