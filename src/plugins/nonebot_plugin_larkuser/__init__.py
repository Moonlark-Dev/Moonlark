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
require("nonebot_plugin_localstore")
require("nonebot_plugin_render")

config = get_plugin_config(Config)

from .matchers import recorder, panel
from .utils.matcher import patch_matcher
from .utils.level import get_level_by_experience
from .utils.user import get_user
