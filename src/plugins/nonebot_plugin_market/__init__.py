from nonebot import require
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-market",
    description="玩家间物品交易市场",
    usage="market [list [page]] | market sell <bag_index> [count] [price_diff] | market buy <name> [count]",
    config=None,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")

from . import __main__
