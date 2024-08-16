from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-join-message",
    description="",
    usage="",
    config=None,
)
require("nonebot_plugin_localstore")
require("nonebot_plugin_larklang")

from . import onebot_11, qq
