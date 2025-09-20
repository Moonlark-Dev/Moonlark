from nonebot import require, load_plugin
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkcave",
    description="Moonlark 回声洞插件",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_localstore")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_render")
require("nonebot_plugin_alconna")
require("nonebot_plugin_schedule")


from . import comment, archiver, api, commands
