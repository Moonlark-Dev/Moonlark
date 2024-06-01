from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_linuxman",
    description="Linux Manpage 查询",
    usage="",
    config=Config,
)

require("nonebot_plugin_htmlrender")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")

from . import __main__
