from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_ranking",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkutils")

from .generator import generate_image
