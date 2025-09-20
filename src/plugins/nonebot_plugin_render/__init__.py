from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-render",
    description="",
    usage="",
    config=Config,
)


require("nonebot_plugin_htmlrender")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")

from .render import render_template, generate_render_keys
from .cache import creator
from . import __main__
