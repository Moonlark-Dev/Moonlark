from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_boothill",
    description="",
    usage="",
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_larklang")

from . import __main__
