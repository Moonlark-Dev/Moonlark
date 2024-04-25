from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_wolfram_alpha",
    description="",
    usage="",
    config=Config,
)

from . import __main__
