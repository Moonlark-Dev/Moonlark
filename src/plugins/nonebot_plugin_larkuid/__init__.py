from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkuid",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_apscheduler")

from . import __main__, middlewares
from . import web
