from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-turtle-soup",
    description="AI 主持的海龟汤（情境猜谜）游戏",
    usage="",
    config=Config,
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_openai")
require("nonebot_plugin_decision")
require("nonebot_plugin_ranking")

from . import models  # ruff: ignore[unused-import, module-import-not-at-top-of-file] - 确保 ORM 模型被注册
from . import matcher as matcher  # ruff: ignore[unused-import, module-import-not-at-top-of-file]
from . import ranking as ranking  # ruff: ignore[unused-import, module-import-not-at-top-of-file]
