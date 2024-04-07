from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import require
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

from . import reviewer
reviewer.api_key = config.baidu_api_key
reviewer.secret_key = config.baidu_secret_key

from .user import get_user_id
from .reviewer import review_image, review_text
from .reply import ReplyExtension