from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-holiday",
    description="假期查询",
    usage="",
    config=None,
)


require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import __main__