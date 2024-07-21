from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_add",
    description="",
    usage="",
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_larkcave:nonebot_plugin_cave_similarity_check")

from . import __main__
