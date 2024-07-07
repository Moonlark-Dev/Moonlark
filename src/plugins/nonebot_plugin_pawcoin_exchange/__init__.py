from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-pawcoin-exchange",
    description="",
    usage="",
    config=Config,
)


require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_bag")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_items")

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")

from . import __main__
