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

from .api import create_minigame_session, get_user_data, get_user_data_list, exchange_pawcoin
from .ranking import get_rank_user
