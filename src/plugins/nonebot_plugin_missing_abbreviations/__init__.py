# ruff: disable[module-import-not-at-top-of-file, non-empty-init-module]
from nonebot import get_driver, require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-missing-abbreviations",
    description="(小游戏) 缩略：通过被缩略的部分猜出缩略词",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_openai")
require("nonebot_plugin_htmlrender")

from . import matcher as matcher


@get_driver().on_startup
async def prefetch_questions_on_startup() -> None:
    """启动时如果本地题目缓存不足就后台补一批，减少第一局的等待时间。"""
    from nonebot_plugin_openai.config import config as openai_config

    from .store import get_question_store

    if not openai_config.openai_api_key:
        return
    store = get_question_store()
    if await store.count() < store.low_water:
        store.schedule_prefetch()


# ruff: enable[module-import-not-at-top-of-file, non-empty-init-module]
