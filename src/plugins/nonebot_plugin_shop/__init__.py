from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_shop",
    description="",
    usage="",
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_items")
require("nonebot_plugin_bag")

from . import __main__
