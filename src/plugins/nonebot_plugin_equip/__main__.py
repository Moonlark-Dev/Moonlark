from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils import get_user_id

from .api import (
    EquipError,
    build_state_text,
    equip_from_bag,
    get_equipment_by_type,
    get_equipped_rows,
    unequip,
)
from .lang import lang
from .registry import get_equipment_by_item_id

alc = Alconna(
    "equip",
    Subcommand("off", Args["type_", str]),
    Args["index?", int],
)
equip = on_alconna(alc)
patch_matcher(equip)


async def get_definition_name(definition, user_id: str) -> str:
    return await lang.text(definition.name_key, user_id)


@equip.assign("$main")
async def _(index: int | None = None, user_id: str = get_user_id()) -> None:
    """查看装备栏，或装备背包中的指定物品"""
    if index is None:
        rows = await get_equipped_rows(user_id)
        if not rows:
            await lang.finish("list.empty", user_id)
        lines = [await lang.text("list.title", user_id)]
        for row in rows:
            definition = get_equipment_by_item_id(row.item_id)
            name = await get_definition_name(definition, user_id) if definition else row.item_id
            state_text = await build_state_text(definition, row, user_id) if definition else ""
            suffix = f"（{state_text}）" if state_text else ""
            lines.append(await lang.text("list.item", user_id, name, suffix))
        lines.append(await lang.text("list.footer", user_id))
        await equip.finish("\n".join(lines))

    try:
        definition = await equip_from_bag(user_id, index)
    except IndexError:
        await lang.finish("use.not_found", user_id)
    except EquipError as error:
        if error.code == "not_equipment":
            await lang.finish("use.not_equipment", user_id)
        if error.code == "already_equipped":
            name = await get_definition_name(error.definition, user_id)
            await lang.finish("use.already_equipped", user_id, name)
        raise
    name = await get_definition_name(definition, user_id)
    await lang.finish("use.success", user_id, name)


@equip.assign("off")
async def _(type_: str, user_id: str = get_user_id()) -> None:
    """卸下指定类型的装备"""
    definition = get_equipment_by_type(type_)
    if definition is None:
        await lang.finish("unequip.invalid_type", user_id, type_)
    try:
        await unequip(user_id, definition.type)
    except EquipError:
        # unequip 只会在没有装备中的装备时抛出 EquipError
        await lang.finish("unequip.not_equipped", user_id)
    name = await get_definition_name(definition, user_id)
    await lang.finish("unequip.success", user_id, name)
