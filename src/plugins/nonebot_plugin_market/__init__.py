from nonebot import require
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-market",
    description="",
    usage="",
    config=None,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")

from . import __main__
