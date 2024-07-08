from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-bots",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_apscheduler")

from . import __main__
