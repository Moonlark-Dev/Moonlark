from nonebot.plugin import PluginMetadata
from nonebot import require

from . import config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-ghot",
    description="群聊热度计算插件",
    usage="/ghot 查看群聊热度",
    config=config.Config,
)

require("nonebot_plugin_message_summary")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")

from .function import get_group_hot_score
