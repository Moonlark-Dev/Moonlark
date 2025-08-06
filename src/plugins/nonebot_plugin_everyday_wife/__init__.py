from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_everyday_wife",
    description="",
    usage="",
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_session")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")
require("nonebot_plugin_userinfo")

from . import __main__
