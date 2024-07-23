from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_archive",
    description="",
    usage="",
)


require("nonebot_plugin_apscheduler")
require("nonebot_plugin_larkcave:nonebot_plugin_cave_comment")

from . import __main__
