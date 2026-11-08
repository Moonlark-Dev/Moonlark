from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-broadcast",
    description="Broadcast plugin for sending messages to multiple groups",
    usage="",
    config=Config,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_localstore")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_orm")
require("nonebot_plugin_bots")
require("nonebot_plugin_larkuid")

from . import groups  # noqa: E402, F401 - 注册群列表跟踪的 event_preprocessor
from . import web  # noqa: E402, F401 - 注册更新公告 Web 接口
from . import __main__
from .__main__ import get_available_groups
from .announcement import has_new_update, load_announcement, mark_update_read  # noqa: E402
from .groups import list_group_snapshots  # noqa: E402

__all__ = [
    "get_available_groups",
    "has_new_update",
    "list_group_snapshots",
    "load_announcement",
    "mark_update_read",
]
