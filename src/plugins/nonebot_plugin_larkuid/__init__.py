from nonebot.plugin import PluginMetadata
from .config import Config
from nonebot import require

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

from . import (
    navbar,
    login,
    verify,
    __main__,
    success,
    user,
    lang_api
)
