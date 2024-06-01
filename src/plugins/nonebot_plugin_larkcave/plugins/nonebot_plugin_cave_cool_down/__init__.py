from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_cool_down",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

from . import __main__
