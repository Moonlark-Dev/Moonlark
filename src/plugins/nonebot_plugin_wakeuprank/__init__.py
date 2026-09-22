from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_wakeuprank",
    description="早起排行插件",
    usage="",
    config=None,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_last_seen")
require("nonebot_plugin_ranking")
require("nonebot_plugin_render")

from . import __main__
