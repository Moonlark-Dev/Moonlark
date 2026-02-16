from nonebot_plugin_alconna import Alconna, Args, Subcommand, Target, get_target, on_alconna
from nonebot.params import Depends
from nonebot_plugin_chat.core.session import get_private_session
from nonebot_plugin_chat.models import RuaData
from nonebot_plugin_chat.models import RuaAction
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_orm import get_session
from nonebot.adapters import Bot, Event
from ..lang import lang

alc = Alconna("rua", Subcommand("action", Args["target_index?", int]))
matcher = on_alconna(alc)

RUA_ACTIONS: dict[int, RuaAction] = {
    1: RuaAction(name="poke", refusable=True, unlock_favorability=0.0),
    2: RuaAction(name="head", refusable=True, unlock_favorability=0.007),
    3: RuaAction(name="chin", refusable=False, unlock_favorability=0.051),
    4: RuaAction(name="cheek", refusable=False, unlock_favorability=0.051),
    5: RuaAction(name="hug", refusable=False, unlock_favorability=0.151),
    6: RuaAction(name="ears", refusable=True, unlock_favorability=0.300),
}


@matcher.assign("target_index")
async def _(target_index: int, user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    try:
        target_action = RUA_ACTIONS[target_index]
    except KeyError:
        await lang.finish("rua.index_error", user_id)
    if user.get_fav() < target_action["unlock_favorability"]:
        await lang.finish("rua.favorability_error", user_id, target_action["unlock_favorability"], user.get_fav())
    async with get_session() as session:
        if (rua_data := await session.get(RuaData, {"user_id": user_id})) is None:
            rua_data = RuaData(user_id=user_id, action_id=target_index)
        else:
            rua_data.action_id = target_index
        await session.merge(rua_data)
        await session.commit()
    await lang.finish("rua.success", user_id, await lang.text(f"rua.actions.{target_action['name']}.name", user_id))


async def get_selected_action(user_id: str) -> RuaAction:
    async with get_session() as session:
        if (rua_data := await session.get(RuaData, {"user_id": user_id})) and rua_data.action_id in RUA_ACTIONS:
            return RUA_ACTIONS[rua_data.action_id]
        else:
            return RUA_ACTIONS[1]  # 默认返回 poke


@matcher.assign("action")
async def _(user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    selected_action = await get_selected_action(user_id)
    actions = []
    for action_id, action in RUA_ACTIONS.items():
        if user.get_fav() < action["unlock_favorability"]:
            continue
        if action["name"] == selected_action["name"]:
            actions.append(
                await lang.text(
                    "rua.action_list_item", user_id, "*", await lang.text(f"rua.actions.{action['name']}.name", user_id)
                )
            )
        else:
            actions.append(
                await lang.text(
                    "rua.action_list_item",
                    user_id,
                    action_id,
                    await lang.text(f"rua.actions.{action['name']}.name", user_id),
                )
            )
    await lang.finish("rua.action_list", user_id, "\n".join(actions))


async def _get_target(event: Event) -> Target:
    return get_target(event)


@matcher.assign("$main")
async def _(
    bot: Bot,
    event: Event,
    target: Target = Depends(_get_target),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    from nonebot_plugin_chat.core.session import get_group_session_forced

    nickname = await get_nickname(user_id, bot, event)
    selected_action = await get_selected_action(user_id)

    if event.get_session_id() == user_id:
        session = await get_private_session(user_id, target, bot)
    else:
        session = await get_group_session_forced(group_id, target, bot)

    await session.handle_rua(nickname, user_id, selected_action)
