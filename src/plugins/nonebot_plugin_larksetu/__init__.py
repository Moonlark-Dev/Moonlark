from pathlib import Path
from nonebot import require
import nonebot
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larksetu",
    description="Moonlark 随机图片",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")
require("nonebot_plugin_saa")
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")

from . import __main__

sub_plugins = nonebot.load_plugins(
    str(Path(__file__).parent.joinpath("plugins").resolve())
)

