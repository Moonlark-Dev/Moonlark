from nonebot.plugin import PluginMetadata
from nonebot import require
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_preview",
    description="Moonlark Preview 插件",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")

from . import __main__



