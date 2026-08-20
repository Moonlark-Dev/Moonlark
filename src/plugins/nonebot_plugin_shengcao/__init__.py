from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-shengcao",
    description="生草机 - 文字同义替换恶搞工具",
    usage="/grass <文本>",
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import main
