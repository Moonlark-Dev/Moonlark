from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-wtfis",
    description="What the fuck it's saying",
    usage="/2048",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_openai")

from . import __main__
