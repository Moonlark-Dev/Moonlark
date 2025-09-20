from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-status",
    description="System status monitoring plugin",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_render")
require("nonebot_plugin_status_report")

from . import __main__ as __main__