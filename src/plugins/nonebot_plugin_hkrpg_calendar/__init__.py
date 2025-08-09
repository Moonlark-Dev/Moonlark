from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-hkrpg-calendar",
    description="崩铁活动日历",
    usage="/hsrc",
    config=None,
)
require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_localstore")

from . import __main__
