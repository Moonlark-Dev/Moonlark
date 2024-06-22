from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata


from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkhelp",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_render")

from . import __main__
