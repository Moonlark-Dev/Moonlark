from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Option,
    Subcommand,
    Target,
    UniMessage,
    get_message_id,
    get_target,
    on_alconna,
)
from nonebot_plugin_chat.config import config
from nonebot_plugin_chat.core.session import get_group_session_forced, get_private_session
from nonebot_plugin_chat.models import RuaData
from nonebot_plugin_chat.types import RuaAction
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_ranking.types import RankingData
from sqlalchemy import select

from ..lang import lang

alc = Alconna(
    "rua",
    Subcommand(
        "action",
        Args["target_index?", int],
        Option("--switch-only|-s"),
        Option("--rua-only|-r"),
    ),
    Args["target_index?", int],
    Subcommand("rank"),
)
matcher = on_alconna(alc)


RUA_ACTIONS: dict[int, RuaAction] = {
    1: RuaAction(name="poke", refusable=True, unlock_favorability=0.0),
    2: RuaAction(name="head", refusable=True, unlock_favorability=0.007),
    3: RuaAction(name="chin", refusable=False, unlock_favorability=0.051),
    4: RuaAction(name="cheek", refusable=False, unlock_favorability=0.051),
    5: RuaAction(name="hug", refusable=False, unlock_favorability=0.151),
    6: RuaAction(name="ears", refusable=True, unlock_favorability=0.300),
}


async def get_selected_action(user_id: str) -> RuaAction:
    async with get_session() as session:
        if (rua_data := await session.get(RuaData, {"user_id": user_id})) and rua_data.action_id in RUA_ACTIONS:
            return RUA_ACTIONS[rua_data.action_id]
        else:
            return RUA_ACTIONS[1]


async def increment_rua_count(user_id: str) -> None:
    async with get_session() as session:
        if (rua_data := await session.get(RuaData, {"user_id": user_id})) is None:
            rua_data = RuaData(user_id=user_id, action_id=1, count=1)
        else:
            rua_data.count += 1
        await session.merge(rua_data)
        await session.commit()


async def _get_target(event: Event) -> Target:
    return get_target(event)


async def execute_rua(
    bot: Bot,
    event: Event,
    target: Target,
    group_id: str,
    user_id: str,
    action: RuaAction,
) -> None:
    nickname = await get_nickname(user_id, bot, event)
    message_id = get_message_id(event)

    if event.get_session_id() == user_id:
        session = await get_private_session(user_id, target, bot)
    else:
        session = await get_group_session_forced(group_id, target, bot)

    session.set_target(target, bot)

    if session.is_napcat_bot():
        await session.processor.send_reaction(message_id, config.rua_reaction_config.pending)
    else:
        await lang.send(f"rua.actions.{action['name']}.received", user_id)

    await increment_rua_count(user_id)
    await session.handle_rua(nickname, user_id, action, message_id)


@matcher.assign("action.target_index")
async def _(
    bot: Bot,
    event: Event,
    target_index: int,
    arp: Arparma,
    target: Target = Depends(_get_target),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    user = await get_user(user_id)
    try:
        target_action = RUA_ACTIONS[target_index]
    except KeyError:
        await lang.finish("rua.index_error", user_id)
    if user.get_fav() < target_action["unlock_favorability"]:
        await lang.finish("rua.favorability_error", user_id, target_action["unlock_favorability"], user.get_fav())

    switch_only = arp.find("action.switch-only")
    rua_only = arp.find("action.rua-only")

    if switch_only and rua_only:
        await matcher.finish("--switch-only 和 --rua-only 不能同时使用")

    if not rua_only:
        async with get_session() as session:
            if (rua_data := await session.get(RuaData, {"user_id": user_id})) is None:
                rua_data = RuaData(user_id=user_id, action_id=target_index)
            else:
                rua_data.action_id = target_index
            await session.merge(rua_data)
            await session.commit()
        await lang.send("rua.success", user_id, await lang.text(f"rua.actions.{target_action['name']}.name", user_id))

    if not switch_only:
        await execute_rua(bot, event, target, group_id, user_id, target_action)


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


@matcher.assign("rank")
async def _(user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        ranked_data = (await session.execute(select(RuaData).order_by(RuaData.count.desc()))).scalars().all()

    if not ranked_data:
        await lang.finish("rua.rank_no_data", user_id)

    ranking_data = [
        RankingData(user_id=data.user_id, data=data.count, info=None) for data in ranked_data if data.count > 0
    ]

    if not ranking_data:
        await lang.finish("rua.rank_no_data", user_id)

    image = await generate_image(ranking_data, user_id, await lang.text("rua.rank_title", user_id))
    await matcher.finish(UniMessage().image(raw=image, name="image.png"))


@matcher.assign("target_index")
async def _(
    bot: Bot,
    event: Event,
    target_index: int,
    target: Target = Depends(_get_target),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    user = await get_user(user_id)
    try:
        target_action = RUA_ACTIONS[target_index]
    except KeyError:
        await lang.finish("rua.index_error", user_id)
    if user.get_fav() < target_action["unlock_favorability"]:
        await lang.finish("rua.favorability_error", user_id, target_action["unlock_favorability"], user.get_fav())

    await execute_rua(bot, event, target, group_id, user_id, target_action)


@matcher.assign("$main")
async def _(
    bot: Bot,
    event: Event,
    target: Target = Depends(_get_target),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    selected_action = await get_selected_action(user_id)
    await execute_rua(bot, event, target, group_id, user_id, selected_action)
