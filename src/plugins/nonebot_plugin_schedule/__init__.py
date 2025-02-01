from nonebot.plugin import PluginMetadata
from nonebot import require
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-schedule",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_render")
require("nonebot_plugin_sign")
require("nonebot_plugin_items")
require("nonebot_plugin_bag")

from . import __main__
from .utils import complete_schedule