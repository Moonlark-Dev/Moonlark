from nonebot.plugin import PluginMetadata
from nonebot import require
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-turn-off-lights",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_alconna")
require("nonebot_plugin_waiter")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_minigame_api")

from . import __main__
