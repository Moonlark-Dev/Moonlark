from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-roll",
    description="",
    usage="",
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larkutils")

from . import __main__  # noqa: F401, E402  # pylint: disable=wrong-import-position
