from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_email",
    description="",
    usage="",
    config=Config,
)
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuid")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")
require("nonebot_plugin_orm")

from .web import create, manage, edit, remove
from . import __main__
from .utils import cleaner
from .commands import email, unread, claim

from .utils.send import send_email, send_global_email
from .types import EmailItemData, DictEmailData
from .utils.unread import get_unread_email, get_unread_email_count
