from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_favrank",
    description="Moonlark 好感度排行",
    usage="fav-rank",
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_ranking")
require("nonebot_plugin_larkuser")

from . import __main__
