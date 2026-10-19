from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_equip",
    description="装备栏：查看、装备、卸下装备，装备激活后提供对应的被动效果",
    usage="",
    config=None,
)

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_items")
require("nonebot_plugin_bag")

from . import models  # noqa: F401, E402 - 确保 ORM 模型被注册
from . import __main__  # noqa: F401, E402
from .api import (  # noqa: F401, E402
    BarrierResult,
    EquipError,
    build_state_text,
    equip_from_bag,
    get_equipped_row,
    get_equipped_rows,
    handle_barrier,
    unequip,
)
from .registry import (  # noqa: F401, E402
    EQUIPMENTS,
    EquipmentDefinition,
    register_equipment,
)
