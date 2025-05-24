from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_sudoku",
    description="数独游戏",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")
require("nonebot_plugin_ranking")
require("nonebot_plugin_waiter")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_achievement")
require("nonebot_plugin_localstore")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")

from . import __main__
