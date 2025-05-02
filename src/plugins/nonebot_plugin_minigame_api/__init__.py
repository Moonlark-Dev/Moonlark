from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-minigames-api",
    description="",
    usage="",
    config=None,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")
require("nonebot_plugin_ranking")
require("nonebot_plugin_alconna")
require("nonebot_plugin_render")
require("nonebot_plugin_larkutils")

from .api import create_minigame_session
from .ranking import get_rank_user
from . import __main__
