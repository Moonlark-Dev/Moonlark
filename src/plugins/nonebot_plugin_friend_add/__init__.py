from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_localstore")

from . import __main__

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-friend-add",
    description="",
    usage="",
    config=Config,
)


