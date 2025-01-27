from nonebot import require
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_github",
    description="",
    usage="",
)


require("nonebot_plugin_render")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import data_source
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot import on_keyword


github_command = on_alconna(Alconna("github", Args["url", str]))
github_keyword = on_keyword({"/"})


@github_command.handle()
async def _(url: str):
    await data_source.github_handler(github_command, url)


@github_keyword.handle()
async def _(url: str):
    await data_source.github_handler(github_keyword, url)

