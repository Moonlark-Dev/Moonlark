from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import require
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
require("nonebot_plugin_larkuid")

config = get_plugin_config(Config)

from .utils.user import (
    get_user,
    set_user_data
)
from .utils.level import (
    get_level_by_experience,
    add_exp
)
from .utils.vimcoin import (
    add_vimcoin,
    use_vimcoin,
    has_vimcoin
)

from . import __main__
from . import recorder
from . import web
from .matcher import patch_matcher
