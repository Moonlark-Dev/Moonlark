from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_buff",
    description="Moonlark 效果（Buff）系统：附着、管理与查询用户当前具有的效果",
    usage="",
)

require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_orm")

from . import models  # noqa: F401, E402 - 确保 ORM 模型被注册
from . import __main__  # noqa: F401, E402
from .api import (  # noqa: F401, E402
    BuffInfo,
    attach_buff,
    clear_buffs,
    consume_buff,
    detach_buff,
    get_buff_attachment,
    get_buff_attachments,
    get_buff_layers,
    has_buff,
)
from .builtin import (  # noqa: F401, E402
    BAD_LUCK_BUFF_ID,
    BAD_LUCK_DURATION,
    BAD_LUCK_MAX_LAYERS,
    attach_bad_luck,
    bad_luck_multiplier,
    get_bad_luck_layers,
    get_bad_luck_multiplier,
)
from .registry import (  # noqa: F401, E402
    BuffDefinition,
    get_buff_definition,
    get_buff_definitions,
    register_buff,
)
