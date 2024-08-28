from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_item")
require("nonebot_plugin_bag")

from . import commands

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-larkstory",
    description="",
    usage="",
    config=Config,
)
