from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_seturank",
    description="Moonlark 随机图片排行",
    usage="",
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larksetu")


from . import __main__
