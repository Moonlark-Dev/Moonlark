from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_access",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_htmlrender")

from . import __main__, web
from .utils import checker
from src.plugins.nonebot_plugin_access.utils.set_access import set_access
