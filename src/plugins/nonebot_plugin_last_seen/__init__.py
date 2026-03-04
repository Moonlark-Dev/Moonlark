from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_last_seen",
    description="记录并检测群员最后上线时间和最后在当前会话上线的时间",
    usage="/lastseen [@用户] | /lastseen here [@用户]",
    type="application",
    homepage="https://github.com/Moonlark-Dev/Moonlark",
    supported_adapters=None,
)

# Required dependencies
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")

from . import __main__
