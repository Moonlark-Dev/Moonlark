from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

from .config import Config, config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkutils",
    description="Moonlark 工具箱",
    usage="",
    config=Config,
)


require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_session")


from . import reviewer

reviewer.api_key = config.baidu_api_key
reviewer.secret_key = config.baidu_secret_key

from .group import get_group_id
from .reviewer import review_image, review_text
from .types import ReviewResult
from .sql import get_id
from .gsc_time import get_galactic_time
from .superuser import is_user_superuser, is_superuser
from .user import get_user_id, is_private_message
from .bot import is_public_qq_bot
from .subaccount import get_main_account, set_main_account
from .user_id import parse_special_user_id
from .file import open_file, FileManager, FileType
from .jrrp import get_luck_value
