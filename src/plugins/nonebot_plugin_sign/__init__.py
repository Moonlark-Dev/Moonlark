from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_sign",
    description="",
    usage="",
    config=Config,
)

# require("nonebot_plugin_ranking")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_email")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_render")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")
require("nonebot_plugin_chat")

from .__main__ import is_user_signed
