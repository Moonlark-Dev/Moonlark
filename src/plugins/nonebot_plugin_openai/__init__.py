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

from .utils.chat import fetch_message
from .utils.message import generate_message
