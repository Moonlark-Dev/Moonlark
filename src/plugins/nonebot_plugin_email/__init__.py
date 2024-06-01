from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_email",
    description="",
    usage="",
    config=Config,
)
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuid")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_orm")
