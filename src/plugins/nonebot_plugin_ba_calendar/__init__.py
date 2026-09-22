from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-ba-calendar",
    description="蔚蓝档案活动日历",
    usage="/bac cn|in|jp\n/bac-remind on|off|server <cn|in|jp>",
    config=None,
)
require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")

from . import __main__
from . import reminder
