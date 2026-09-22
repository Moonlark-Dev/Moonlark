"""Buff 定义注册表。

其他插件可以在自己的模块导入时调用 `register_buff` 声明自己使用的 buff，
`/buff` 指令会依据注册表展示名称与说明。未注册的 buff 仍然可以附着，
但会以 buff id 作为名称并在日志中给出警告。
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from nonebot.log import logger


@dataclass(frozen=True)
class BuffDefinition:
    """一种 buff 的静态定义

    Attributes:
        id: buff 唯一标识，建议使用 `namespace:name` 形式
        name_key: 展示名称在 lang 文件中的键
        description_key: 说明文本在 lang 文件中的键，留空表示没有说明
        lang_plugin: `name_key` / `description_key` 所属的插件语言文件
        max_layers: 最大层数；1 表示不支持叠加，大于 1 表示支持叠加
        default_duration: 未显式指定时间维度时使用的默认持续时间
        default_count: 未显式指定次数维度时使用的默认触发次数
    """

    id: str
    name_key: str
    description_key: str = ""
    lang_plugin: str = "buff"
    max_layers: int = 1
    default_duration: Optional[timedelta] = None
    default_count: Optional[int] = None

    @property
    def stackable(self) -> bool:
        return self.max_layers > 1


_buff_definitions: dict[str, BuffDefinition] = {}


def register_buff(definition: BuffDefinition) -> BuffDefinition:
    """注册一个 buff 定义并返回它，便于在模块顶层直接使用返回值"""
    _buff_definitions[definition.id] = definition
    logger.debug(f"已注册 buff 定义: {definition.id} (max_layers={definition.max_layers})")
    return definition


def get_buff_definition(buff_id: str) -> Optional[BuffDefinition]:
    """获取 buff 定义；未注册时返回 None"""
    return _buff_definitions.get(buff_id)


def get_buff_definitions() -> dict[str, BuffDefinition]:
    return dict(_buff_definitions)


def ensure_buff_definition(buff_id: str) -> BuffDefinition:
    """获取 buff 定义，未注册时自动补一个占位定义并给出警告"""
    definition = get_buff_definition(buff_id)
    if definition is not None:
        return definition
    logger.warning(f"buff {buff_id} 未注册定义，已按默认行为处理（不支持叠加，无默认时长/次数）")
    return register_buff(BuffDefinition(id=buff_id, name_key=buff_id))
