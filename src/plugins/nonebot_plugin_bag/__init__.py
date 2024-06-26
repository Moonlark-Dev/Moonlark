from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-bag",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_item")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_render")

from .commands import bag
