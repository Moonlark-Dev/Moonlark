from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkhelp",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

from nonebot import require

require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_saa")

from . import __main__
