from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_render")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkhelp",
    description="",
    usage="",
    config=Config,
)

from . import __main__, api, cache
