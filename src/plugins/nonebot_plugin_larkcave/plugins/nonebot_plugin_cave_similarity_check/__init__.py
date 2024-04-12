from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_similarity_check",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkcave")

from .text import check_text_content
