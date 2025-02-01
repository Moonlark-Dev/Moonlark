from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-hello",
    description="",
    usage="",
    config=Config,
)
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larklang")
# require("nonebot_plugin_openai")
require("nonebot_plugin_schedule")

from . import main as __main
