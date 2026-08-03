from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_eggstrike",
    description="(游戏) 砸鸡蛋",
    usage="",
    config=None,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_items")
require("nonebot_plugin_bag")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_ranking")
require("nonebot_plugin_render")

from . import __main__
