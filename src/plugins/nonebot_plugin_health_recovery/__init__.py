from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_health_recovery",
    description="HP 恢复插件：每小时为最近一小时内活跃的已注册用户回复 5 点 HP",
    usage="",
    config=None,
)

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_last_seen")

from . import __main__
