from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-status-report",
    description="Status report API",
    usage="",
    config=Config,
)

require("nonebot_plugin_bots")
require("nonebot_plugin_localstore")

from .__main__ import report_openai_history
