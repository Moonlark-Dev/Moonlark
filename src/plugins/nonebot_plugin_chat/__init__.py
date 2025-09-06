from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-chat",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_larklang")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_openai")
require("nonebot_plugin_wolfram_alpha")
require("nonebot_plugin_alconna")

from . import matcher
