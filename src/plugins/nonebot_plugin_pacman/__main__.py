from pathlib import Path

from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot_plugin_htmlrender import template_to_pic

from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils.user import get_user_id
from .data import search_package
from .exception import NoResultException

lang = LangHelper()

alc = Alconna("pacman", Args["keyword", str])
pacman = on_alconna(alc)


@pacman.handle()
async def _(keyword: str, user_id: str = get_user_id()) -> None:
    try:
        packages = await search_package(keyword)
    except NoResultException:
        await lang.finish("search.not_found", user_id, keyword)
        return
    image = await template_to_pic(
        Path(__file__).parent.joinpath("templates").as_posix(),
        "index.html.jinja",
        {
            "title": await lang.text("image.title", user_id),
            "source": await lang.text("image.source", user_id),
            "footer": await lang.text("image.footer", user_id),
            "packages": packages,
            "out_of_date": await lang.text("image.out_of_date", user_id),
        },
    )
    await pacman.finish(UniMessage().image(raw=image))
