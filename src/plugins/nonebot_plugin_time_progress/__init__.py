from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")


__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_time_progress",
    description="时间进度查看与年进度推送",
    usage="time-progress / time-progress sub [on/off]",
)


from . import __main__
from . import reminder
