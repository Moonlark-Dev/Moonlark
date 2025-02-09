from sqlalchemy import select
from ...models import CaveData
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.user import MoonlarkGuestUser
from ...lang import lang


async def get_poster_data(session: async_scoped_session) -> dict[str, int]:
    posters = {}
    for poster in await session.scalars(select(CaveData.author).where(CaveData.public == True)):
        if poster in posters:
            posters[poster] += 1
        else:
            posters[poster] = 1
    return posters


async def set_nickname_for_posters(data: dict[str, int], sender_id: str) -> dict[str, int]:
    other_key_name = await lang.text("stat.other", sender_id)
    posters = {}
    for user_id, count in data.items():
        user = await get_user(user_id)
        if not user.has_nickname():
            posters[other_key_name] = count + posters.get(other_key_name, 0)
            continue
        nickname = user.get_nickname()
        posters[nickname] = count + posters.get(nickname, 0)
    return posters


async def merge_small_poster(data: dict[str, int], sender_id: str) -> dict[str, int]:
    posters = {}
    lowest = max(sum([i for i in data.values()]) / len(data) * 0.05, 3)
    other_key_name = await lang.text("stat.other", sender_id)
    for key, count in data.items():
        if key == other_key_name:
            continue
        elif count < lowest:
            posters[other_key_name] = count + posters.get(other_key_name, 0)
        else:
            posters[key] = count
    return posters
