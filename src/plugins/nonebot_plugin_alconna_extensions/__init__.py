from nonebot import get_plugin_config, require
from nonebot.log import logger
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(name="nonebot_plugin_alconna_extensions", description="", usage="")

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna.extension import load_from_path


EXTENSIONS = [
    "@reply:ReplyMergeExtension",
    "nonebot_plugin_alconna_extensions.global_extensions:UnmatchedExtension",
]
for extension in EXTENSIONS:
    load_from_path(extension)
    logger.info(f"已加载插件 {extension}")
