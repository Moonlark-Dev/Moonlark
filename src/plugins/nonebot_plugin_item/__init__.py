from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-item",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
