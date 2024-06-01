from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkutils",
    description="Moonlark 工具箱",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_session")


from . import reviewer

reviewer.api_key = config.baidu_api_key
reviewer.secret_key = config.baidu_secret_key

from .group import get_group_id
from .html import escape_html
from .reviewer import review_image, review_text
from .sql import get_id
from .superuser import is_superuser
from .user import get_user_id
