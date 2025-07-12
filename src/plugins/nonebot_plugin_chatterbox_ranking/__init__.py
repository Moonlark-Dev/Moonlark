from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-chatterbox-ranking",
    description="话痨排行",
    usage="",
    config=None,
)


require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")

from . import __main__
