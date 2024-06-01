from nonebot import require
from nonebot.plugin import PluginMetadata

from .web import lang_api, login, navbar, success, user, verify

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkuid",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_larklang")

from . import __main__
