from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-wtfis",
    description="What the fuck it's saying",
    usage="/wtfis",
    config=None,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_openai")

from . import __main__
