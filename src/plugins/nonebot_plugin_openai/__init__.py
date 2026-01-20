from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-openai",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_status_report")
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")

from .utils.chat import fetch_message, MessageFetcher
from .utils.message import generate_message
from .commands import model as _  # noqa: F401
