from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-message-summary",
    description="AI 历史消息总结",
    usage="",
    config=None,
)


require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larklang")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_openai")
require("nonebot_plugin_orm")
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")

from . import __main__
