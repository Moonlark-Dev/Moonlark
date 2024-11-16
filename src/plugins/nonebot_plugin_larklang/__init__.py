from nonebot.plugin import PluginMetadata, require

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larklang",
    description="Moonlark 本地化插件",
    usage="",
    config=Config,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")

from . import command as _command
from .__main__ import LangHelper
