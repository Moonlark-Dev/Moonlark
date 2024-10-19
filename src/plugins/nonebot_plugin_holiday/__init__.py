from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-holiday",
    description="本年剩余假期",
    usage="/holiday",
    config=None,
)
require("nonebot_plugin_alconna")
require("nonebot_plugin_preview")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import __main__