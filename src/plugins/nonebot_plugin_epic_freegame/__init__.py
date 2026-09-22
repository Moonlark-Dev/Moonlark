from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-epic-freegame",
    description="Epic 免费游戏查询",
    usage="/epic-free",
    config=None,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_render")

from . import __main__
