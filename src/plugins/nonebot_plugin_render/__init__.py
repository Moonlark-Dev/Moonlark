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

from .render import render_template
