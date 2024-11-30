from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-luxun-works",
    description="",
    usage="",
    config=Config,
)
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import main
