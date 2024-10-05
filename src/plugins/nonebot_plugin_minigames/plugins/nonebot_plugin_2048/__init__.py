from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-2048",
    description="2048 小游戏",
    usage="/2048",
    config=Config,
)

require("nonebot_plugin_minigames_api")
require("nonebot_plugin_larklang")
require("nonebot_plugin_finding_the_trail")
require("nonebot_plugin_waiter")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")

from . import __main__
