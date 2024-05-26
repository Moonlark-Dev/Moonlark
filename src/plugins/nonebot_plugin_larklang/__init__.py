from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larklang",
    description="Moonlark 本地化插件",
    usage="",
    config=Config,
)

from nonebot import require
require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")

from .__main__ import LangHelper
from . import command as _command