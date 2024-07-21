from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_restore",
    description="",
    usage="",
)


require("nonebot_plugin_larkcave:nonebot_plugin_cave_remove")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")

from . import __main__
