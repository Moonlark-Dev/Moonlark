from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_market",
    description="玩家间物品交易市场",
    usage="market [list [页码]] | market sell <背包编号> [数量] [价格] | market buy <名称|编号> [数量]",
)

require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")

from . import __main__ as __main__
