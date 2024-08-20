from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-defuse-tnt",
    description="(小游戏) 拆除 TNT",
    usage="",
    config=None,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_render")
require("nonebot_plugin_waiter")
require("nonebot_plugin_alconna")

from . import __main__
