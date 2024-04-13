from nonebot.plugin import PluginMetadata
from nonebot import require
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_remove",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkcave")
require("nonebot_plugin_localstore")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")

from . import __main__