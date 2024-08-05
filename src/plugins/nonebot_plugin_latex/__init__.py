from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-latex",
    description="将 LaTeX 表达式渲染为图片",
    usage="",
    config=None,
)


require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_htmlrender")

from . import __main__