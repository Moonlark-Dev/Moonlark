from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-bag",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_items")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_htmlrender")


from .commands import bag, drop, move, show, tidy, use
from .commands.overflow import get, show, overflow
from .utils import unlock

from .utils.give import give_item_by_list, give_item_by_data
from .utils.item import get_bag_item, get_bag_items, get_items_count
