from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna

from .theme import get_user_theme, get_themes, set_theme
from .lang import lang
from ..nonebot_plugin_larkutils.user import get_user_id

theme = on_alconna(Alconna("theme", Args["name?", str]))


@theme.handle()
async def _(name: Match[str], user_id: str = get_user_id()) -> None:
    if name.available:
        await set_theme(user_id, name.result)
        await lang.finish("command.success", user_id)
    await lang.finish("command.list", user_id, await get_user_theme(user_id), "\n".join(list(await get_themes())))
