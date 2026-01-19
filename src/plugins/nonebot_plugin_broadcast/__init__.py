from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-broadcast",
    description="Broadcast plugin for sending messages to multiple groups",
    usage="",
    config=None,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_localstore")
require("nonebot_plugin_htmlrender")


from . import __main__
from .__main__ import get_available_groups
