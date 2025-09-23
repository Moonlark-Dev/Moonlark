from nonebot import require
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-items",
    description="",
    usage="",
)

require("nonebot_plugin_larklang")


from . import items
from .base.item import Item
from .base.stack import ItemStack
from .base.properties import ItemProperties, get_properties
from .base.useable import UseableItem
from .registry import registry
