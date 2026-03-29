from nonebot_plugin_alconna import Alconna, Args, Option, Subcommand, Target, UniMessage, get_target, on_alconna, get_message_id
from nonebot.params import Depends
from nonebot_plugin_chat.core.session import get_private_session
from nonebot_plugin_chat.models import RuaData
from nonebot_plugin_chat.types import RuaAction
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_orm import get_session
from nonebot.adapters import Bot, Event
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

# Reaction emoji IDs for rua command
RUA_REACTION_PENDING = "181"  # 响应中
RUA_REACTION_ENJOY = ["66", "76"]  # 享受（随机）
RUA_REACTION_DODGE = "10"  # 躲开
RUA_REACTION_BITE = "128074"  # 咬

RUA_ACTIONS: dict[int, RuaAction] = {
    1: RuaAction(name="poke", refusable=True, unlock_favorability=0.0),
    2: RuaAction(name="head", refusable=True, unlock_favorability=0.007),
    3: RuaAction(name="chin", refusable=False, unlock_favorability=0.051),
    4: RuaAction(name="cheek", refusable=False, unlock_favorability=0.051),
    5: RuaAction(name="hug", refusable=False, unlock_favorability=0.151),
    6: RuaAction(name="ears", refusable=True, unlock_favorability=0.300),
}


@matcher.assign("action.target_index")
async def _(
    bot: Bot,
    event: Event,
    target_index: int,
    target: Target = Depends(_get_target),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    from nonebot.matcher import current_matcher
    from nonebot_plugin_alconna import AlconnaResult

    user = await get_user(user_id)
    try:
        target_action = RUA_ACTIONS[target_index]
    except KeyError:
        await lang.finish("rua.index_error", user_id)
    if user.get_fav() < target_action["unlock_favorability"]:
        await lang.finish("rua.favorability_error", user_id, target_action["unlock_favorability"], user.get_fav())

    result: AlconnaResult = current_matcher.get().state["_alc_result"]
    switch_only = result.find("action.switch-only")
    rua_only = result.find("action.rua-only")

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
        from nonebot_plugin_chat.core.session import get_group_session_forced

        nickname = await get_nickname(user_id, bot, event)
        selected_action = target_action if rua_only else await get_selected_action(user_id)
        message_id = get_message_id(event)

        if event.get_session_id() == user_id:
            session = await get_private_session(user_id, target, bot)
        else:
            session = await get_group_session_forced(group_id, target, bot)

        rua_reaction_config = {
            "pending": RUA_REACTION_PENDING,
            "enjoy": RUA_REACTION_ENJOY,
            "dodge": RUA_REACTION_DODGE,
            "bite": RUA_REACTION_BITE,
        }

        if session.is_napcat_bot():
            await session.processor.send_reaction(message_id, RUA_REACTION_PENDING)
        else:
            await lang.send(f"rua.actions.{selected_action['name']}.received", user_id)

        await increment_rua_count(user_id)
        await session.handle_rua(nickname, user_id, selected_action, message_id, rua_reaction_config)


async def get_selected_action(user_id: str) -> RuaAction:
    async with get_session() as session:
        if (rua_data := await session.get(RuaData, {"user_id": user_id})) and rua_data.action_id in RUA_ACTIONS:
            return RUA_ACTIONS[rua_data.action_id]
        else:
            return RUA_ACTIONS[1]  # 默认返回 poke


async def increment_rua_count(user_id: str) -> None:
    async with get_session() as session:
        if (rua_data := await session.get(RuaData, {"user_id": user_id})) is None:
            rua_data = RuaData(user_id=user_id, action_id=1, count=1)
        else:
            rua_data.count += 1
        await session.merge(rua_data)
        await session.commit()


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
        {"user_id": data.user_id, "info": None, "data": data.count} for data in ranked_data if data.count > 0
    ]

    if not ranking_data:
        await lang.finish("rua.rank_no_data", user_id)

    image = await generate_image(ranking_data, user_id, await lang.text("rua.rank_title", user_id))
    await matcher.finish(UniMessage().image(raw=image, name="image.png"))


async def _get_target(event: Event) -> Target:
    return get_target(event)


@matcher.assign("target_index")
async def _(
    bot: Bot,
    event: Event,
    target_index: int,
    target: Target = Depends(_get_target),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    from nonebot_plugin_chat.core.session import get_group_session_forced

    user = await get_user(user_id)
    try:
        target_action = RUA_ACTIONS[target_index]
    except KeyError:
        await lang.finish("rua.index_error", user_id)
    if user.get_fav() < target_action["unlock_favorability"]:
        await lang.finish("rua.favorability_error", user_id, target_action["unlock_favorability"], user.get_fav())

    nickname = await get_nickname(user_id, bot, event)
    message_id = get_message_id(event)

    if event.get_session_id() == user_id:
        session = await get_private_session(user_id, target, bot)
    else:
        session = await get_group_session_forced(group_id, target, bot)

    rua_reaction_config = {
        "pending": RUA_REACTION_PENDING,
        "enjoy": RUA_REACTION_ENJOY,
        "dodge": RUA_REACTION_DODGE,
        "bite": RUA_REACTION_BITE,
    }

    if session.is_napcat_bot():
        await session.processor.send_reaction(message_id, RUA_REACTION_PENDING)
    else:
        await lang.send(f"rua.actions.{target_action['name']}.received", user_id)

    await increment_rua_count(user_id)
    await session.handle_rua(nickname, user_id, target_action, message_id, rua_reaction_config)


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
    message_id = get_message_id(event)

    if event.get_session_id() == user_id:
        session = await get_private_session(user_id, target, bot)
    else:
        session = await get_group_session_forced(group_id, target, bot)

    # Reaction 配置
    rua_reaction_config = {
        "pending": RUA_REACTION_PENDING,
        "enjoy": RUA_REACTION_ENJOY,
        "dodge": RUA_REACTION_DODGE,
        "bite": RUA_REACTION_BITE,
    }

    # 尝试发送 reaction 表示响应中
    if session.is_napcat_bot():
        await session.processor.send_reaction(message_id, RUA_REACTION_PENDING)
    else:
        await lang.send(f"rua.actions.{selected_action['name']}.received", user_id)

    await increment_rua_count(user_id)
    await session.handle_rua(nickname, user_id, selected_action, message_id, rua_reaction_config)
