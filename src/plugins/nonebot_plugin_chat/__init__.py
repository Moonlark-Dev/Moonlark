from nonebot import require, get_driver
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-chat",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_larklang")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_openai")
require("nonebot_plugin_wolfram_alpha")
require("nonebot_plugin_ghot")
require("nonebot_plugin_alconna")

from . import matcher

# 启动时初始化表情包感知哈希
driver = get_driver()


@driver.on_startup
async def _init_sticker_hashes():
    from .utils.hash_initializer import initialize_sticker_hashes

    await initialize_sticker_hashes()


@driver.on_startup
async def _init_sticker_classifications():
    from .utils.hash_initializer import initialize_sticker_classifications

    await initialize_sticker_classifications()
