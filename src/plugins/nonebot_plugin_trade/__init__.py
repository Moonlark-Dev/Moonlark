from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_trade",
    description="模拟股票市场",
    usage="trade | trade buy <股数|比例|all> | trade sell <股数|all> | trade history | trade rank",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")

from . import models  # ruff: ignore[unused-import, module-import-not-at-top-of-file] - 确保 ORM 模型被注册
from . import __main__ as __main__  # ruff: ignore[unused-import, module-import-not-at-top-of-file]
