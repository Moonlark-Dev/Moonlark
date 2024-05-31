from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkuser",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_htmlrender")

config = get_plugin_config(Config)

from . import __main__, recorder
from .matcher import patch_matcher
from .utils.level import add_exp, get_level_by_experience
from .utils.user import get_user, set_user_data
from .utils.vimcoin import add_vimcoin, has_vimcoin, use_vimcoin
