from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-chat-monitor",
    description="Chat Monitor API and WebSocket for Moonlark chat monitoring",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_bots")
require("nonebot_plugin_chat")

from . import __main__  # noqa: E402, F401
