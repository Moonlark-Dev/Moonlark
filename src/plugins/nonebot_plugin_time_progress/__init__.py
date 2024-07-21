from nonebot import require
from nonebot.plugin import PluginMetadata


require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")


__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_time_progress",
    description="",
    usage="",
)


from . import __main__
