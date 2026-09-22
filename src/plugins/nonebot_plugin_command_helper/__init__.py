from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(name="nonebot_plugin_command_helper", description="", usage="")


require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkhelp")
require("nonebot_plugin_openai")

from . import __main__
