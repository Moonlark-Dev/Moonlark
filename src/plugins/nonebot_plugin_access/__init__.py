from nonebot import get_driver, logger, require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_access",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_orm")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

from . import __main__, web
from .utils import checker
from .utils.cache import access_cache
from nonebot_plugin_access.utils.set_access import set_access

driver = get_driver()


@driver.on_startup
async def _load_access_cache() -> None:
    """启动时把权限表拉取到内存。"""
    await access_cache.reload()


@scheduler.scheduled_job("interval", minutes=5, id="access_cache_reload")
async def _reload_access_cache() -> None:
    """每 5 分钟刷新一次权限表；失败时保留上一次的缓存继续服务。"""
    try:
        await access_cache.reload()
    except Exception:
        logger.exception("权限表定时刷新失败，继续使用上一次的缓存")
