from nonebot import require
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_statisics",
    description="",
    usage="",
    config=None,
)

require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")

from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import UniMessage
from ...lang import lang
from ...__main__ import cave
from .data import merge_small_poster, set_nickname_for_posters, get_poster_data
from .image import render_pie


@cave.assign("statisics")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    await lang.send("stat.tip", user_id)
    data = await merge_small_poster(await set_nickname_for_posters(await get_poster_data(session)), user_id)
    img = await render_pie(data, user_id)
    await cave.finish(UniMessage().image(raw=img))



