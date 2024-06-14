from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-quick-math",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")
require("nonebot_plugin_ranking")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_alconna")

