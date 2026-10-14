"""装备定义注册表。

每种装备类型同时只能装备一件；新装备在 :data:`EQUIPMENTS` 注册后即可通过
``/equip`` 装备、卸下并在 ``/equip`` 列表展示。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EquipmentDefinition:
    """一种装备的静态定义

    Attributes:
        type: 装备类型标识（同类型同时只能装备一件）
        item_id: 对应的物品 ID
        name_key: 装备名称在 lang 文件中的键
        description_key: 说明文本在 lang 文件中的键，留空表示没有说明
        state_keys: 该装备保存的状态字段与初始值（如屏障的剩余抵挡次数）
    """

    type: str
    item_id: str
    name_key: str
    description_key: str = ""
    state_keys: dict[str, int] = field(default_factory=dict)


#: 物品 ID -> 装备定义
EQUIPMENTS: dict[str, EquipmentDefinition] = {}

# 临时屏障：装备后每件可阻挡 20 次 splat 攻击，被击中时 2% 概率反弹攻击者
TEMP_BARRIER_ITEM_ID = "moonlark:temp_barrier"
TEMP_BARRIER_BLOCKS = 20
BARRIER_REFLECT_PROBABILITY = 0.02
# 臭鸡蛋 Ex 每次攻击有 80% 概率击穿屏障（不消耗抵挡次数）
BARRIER_EX_PIERCE_PROBABILITY = 0.8


def register_equipment(definition: EquipmentDefinition) -> EquipmentDefinition:
    """注册一个装备定义并返回它"""
    EQUIPMENTS[definition.item_id] = definition
    return definition


def get_equipment_by_item_id(item_id: str) -> EquipmentDefinition | None:
    return EQUIPMENTS.get(item_id)


def get_equipment_by_type(equipment_type: str) -> EquipmentDefinition | None:
    for definition in EQUIPMENTS.values():
        if definition.type == equipment_type:
            return definition
    return None


register_equipment(
    EquipmentDefinition(
        type="temp_barrier",
        item_id=TEMP_BARRIER_ITEM_ID,
        name_key="equipment.temp_barrier.name",
        description_key="equipment.temp_barrier.description",
        state_keys={"blocks": TEMP_BARRIER_BLOCKS},
    ),
)
