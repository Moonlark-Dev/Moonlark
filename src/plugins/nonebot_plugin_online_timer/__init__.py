from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_online_timer",
    description="统计用户在线时间段的插件",
    usage="/online-timer [@用户]",
    type="application",
    homepage="https://github.com/Moonlark-Dev/Moonlark",
    supported_adapters=None,
)

# Required dependencies
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_render")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_ranking")

from . import __main__
