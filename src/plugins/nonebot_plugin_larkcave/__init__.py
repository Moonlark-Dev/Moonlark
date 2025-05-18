from nonebot import require, load_plugin
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkcave",
    description="Moonlark 回声洞插件",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_localstore")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_schedule")

load_plugin("nonebot_plugin_larkcave.plugins.similarity_check")
load_plugin("nonebot_plugin_larkcave.plugins.comment")
load_plugin("nonebot_plugin_larkcave.plugins.add")
load_plugin("nonebot_plugin_larkcave.plugins.statisics")
load_plugin("nonebot_plugin_larkcave.plugins.remove")
load_plugin("nonebot_plugin_larkcave.plugins.restore")
load_plugin("nonebot_plugin_larkcave.plugins.archive")
load_plugin("nonebot_plugin_larkcave.plugins.cool_down")
load_plugin("nonebot_plugin_larkcave.plugins.get")
load_plugin("nonebot_plugin_larkcave.plugins.api")

from . import __main__
