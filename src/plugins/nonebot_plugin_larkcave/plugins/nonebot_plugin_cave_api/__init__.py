from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_api",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkuser")

from . import __main__
from . import image_api