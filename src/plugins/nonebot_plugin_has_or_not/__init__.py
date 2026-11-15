from nonebot import get_driver, require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-has-or-not",
    description="(小游戏) 有无有无：根据提示词猜答案",
    usage="",
    config=Config,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_openai")
require("nonebot_plugin_decision")
require("nonebot_plugin_htmlrender")

from . import matcher  # noqa: E402


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
