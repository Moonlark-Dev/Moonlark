from pathlib import Path
from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_comment",
    description="",
    usage="",
    config=Config,
)



require("nonebot_plugin_larkcave")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_htmlrender")

from . import __main__




