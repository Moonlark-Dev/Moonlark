from nonebot import require, load_plugin, get_driver
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larkcave",
    description="Moonlark 回声洞插件",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_localstore")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_render")
require("nonebot_plugin_alconna")
require("nonebot_plugin_schedule")


from . import comment, archiver, api, commands

# 启动时初始化感知哈希
driver = get_driver()


@driver.on_startup
async def _():
    from .utils.hash_initializer import check_and_update_hashes
    
    await check_and_update_hashes()
