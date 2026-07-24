from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(name="nonebot_plugin_jrrp", description="", usage="")

require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_ranking")
require("nonebot_plugin_orm")
require("nonebot_plugin_schedule")
require("nonebot_plugin_render")
require("nonebot_plugin_apscheduler")

from . import models  # noqa: F401 - 确保 ORM 模型被注册
from . import __main__
from . import rank
