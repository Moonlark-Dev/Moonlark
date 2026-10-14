from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_craft",
    description="合成机：投入原料与 VimCoin，等待一段时间获得产物",
    usage="",
    config=None,
)

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_items")
require("nonebot_plugin_bag")

from . import models  # noqa: F401, E402 - 确保 ORM 模型被注册
from .recipes import MAX_LEVEL, RECIPES  # noqa: F401, E402
from .utils import (  # noqa: F401, E402
    NoFreeSlot,
    NotEnoughMaterial,
    NotEnoughVimcoin,
    collect_finished_jobs,
    get_machine,
    get_running_jobs,
    get_slots_info,
    get_upgrade_cost,
    start_job,
    try_upgrade,
)

from . import __main__  # noqa: F401, E402
