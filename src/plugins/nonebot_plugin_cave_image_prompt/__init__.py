from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_image_prompt",
    description="Cave 图片投稿提示插件",
    usage="向机器人私聊发送单张图片时，询问是否投稿到 Cave",
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_waiter")
require("nonebot_plugin_larkcave")

from . import __main__ as __main__