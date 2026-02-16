from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-chat",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_larklang")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_openai")
require("nonebot_plugin_wolfram_alpha")
require("nonebot_plugin_ghot")
require("nonebot_plugin_alconna")

from . import matcher as _command_matchers
from .core import matchers as _core_matchers
from . import startup as _startup

# 导出供其他插件使用的接口
from .core.session import post_group_event
