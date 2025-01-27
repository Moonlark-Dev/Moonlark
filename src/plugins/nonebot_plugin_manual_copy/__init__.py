from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-manual-copy",
    description="",
    usage="",
    config=Config,
)
require("nonebot_plugin_minigame_api")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")


from . import main
