from nonebot.plugin import PluginMetadata
from .config import Config
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_vote",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_htmlrender")



from . import __main__