from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_pacman",
    description="",
    usage="",
)


require("nonebot_plugin_render")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import __main__
