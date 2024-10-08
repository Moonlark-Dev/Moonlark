from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot.log import logger
from ..nonebot_plugin_render.render import render_template
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils.user import get_user_id
from .data import search_package
from .exceptions import NoResultException

lang = LangHelper()

alc = Alconna("pacman", Args["keyword", str])
pacman = on_alconna(alc)


@pacman.handle()
async def _(keyword: str, user_id: str = get_user_id()) -> None:
    try:
        packages = await search_package(keyword)
    except NoResultException:
        logger.waring(f"{traceback.format_exc()}")
        await lang.finish("search.not_found", user_id, keyword)
        return
    image = await render_template(
        "pacman.html.jinja",
        await lang.text("image.title", user_id),
        user_id,
        {
            "source": await lang.text("image.source", user_id),
            "packages": packages,
            "out_of_date": await lang.text("image.out_of_date", user_id),
        },
    )
    await pacman.finish(UniMessage().image(raw=image))
