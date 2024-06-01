from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_restore",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

require("nonebot_plugin_larkcave:nonebot_plugin_cave_remove")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")

from . import __main__