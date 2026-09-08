from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Match

from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_larkutils.user import is_private_message

from ..__main__ import lang, quick_math
from ..config import config
from ..commands.main import get_qq_user_id
from ..utils.pvp import QuickMathRoom, QuickMathRoomPlayer, find_room_of_user, generate_room_code, rooms


@quick_math.assign("pvp")
async def pvp_help_handler(user_id: str = get_user_id()) -> None:
    await lang.finish("pvp.help", user_id)


@quick_math.assign("pvp.create")
async def create_handler(
    bot: Bot,
    event: Event,
    max_players: Match[int],
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    if private:
        await lang.finish("pvp.only_group", user_id)
    if find_room_of_user(user_id) is not None:
        await lang.finish("pvp.already_in", user_id)
    count = max_players.result if max_players.available else config.qm_pvp_default_max_players
    count = min(max(count, 2), config.qm_pvp_max_players)
    room = QuickMathRoom(generate_room_code(), group_id, user_id, count, bot, event)
    rooms[room.room_id] = room
    room.players.append(QuickMathRoomPlayer(user_id, get_qq_user_id(bot, event), event))
    message = await room.build_create_message(user_id)
    await message.send(target=event, bot=bot)
    await quick_math.finish()


@quick_math.assign("pvp.join")
async def join_handler(
    bot: Bot,
    event: Event,
    room_id: str,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    if private:
        await lang.finish("pvp.only_group", user_id)
    room = rooms.get(room_id.strip().upper())
    if room is None or room.group_id != group_id:
        await lang.finish("pvp.not_found", user_id)
    if room.status != "waiting":
        await lang.finish("pvp.playing", user_id)
    if room.get_player(user_id) is not None:
        await lang.finish("pvp.already_in_room", user_id)
    if room.is_full:
        await lang.finish("pvp.full", user_id)
    if (current := find_room_of_user(user_id)) is not None and current is not room:
        await lang.finish("pvp.already_in", user_id)
    room.players.append(QuickMathRoomPlayer(user_id, get_qq_user_id(bot, event), event))
    room.last_event = event
    message = await room.build_player_list_message(user_id)
    await message.send(target=event, bot=bot)
    await quick_math.finish()


@quick_math.assign("pvp.quit")
async def quit_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    if private:
        await lang.finish("pvp.only_group", user_id)
    room = find_room_of_user(user_id)
    if room is None or room.group_id != group_id:
        await lang.finish("pvp.not_in_room", user_id)
    room.last_event = event
    player = room.get_player(user_id)
    if player is None:
        await quick_math.finish()
    if room.owner == user_id:
        # 房主退出直接解散房间
        room.status = "ended"
        rooms.pop(room.room_id, None)
        await room.broadcast_lang("pvp.disband", user_id)
    elif room.status == "playing":
        # 对局中退出视为淘汰，保存当前成绩
        room.players.remove(player)
        await room.eliminate(player, quit_game=True)
    else:
        room.players.remove(player)
        await room.broadcast_lang("pvp.player_quited", user_id, await room.get_nickname(user_id))
    await quick_math.finish()


@quick_math.assign("pvp.start")
async def start_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    if private:
        await lang.finish("pvp.only_group", user_id)
    room = find_room_of_user(user_id)
    if room is None or room.group_id != group_id:
        await lang.finish("pvp.not_in_room", user_id)
    if room.status != "waiting":
        await lang.finish("pvp.playing", user_id)
    if room.owner != user_id:
        await lang.finish("pvp.not_owner", user_id)
    if len(room.players) < 2:
        await lang.finish("pvp.need_more_players", user_id)
    room.last_event = event
    await room.start()
    await quick_math.finish()
