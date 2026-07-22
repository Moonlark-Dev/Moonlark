from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-qsend",
    description="QQ adapter debug send interface",
    usage="/send <text>",
    config=None,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")

from . import __main__
