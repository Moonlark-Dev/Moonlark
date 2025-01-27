from pathlib import Path

import nonebot
from nonebot import require
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
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")

from . import __main__

nonebot.load_plugin("nonebot_plugin_larksetu.plugins.nonebot_plugin_seturank")
