from sqlalchemy import select
from ...models import CaveData
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkuser import get_user
from ...lang import lang


async def get_poster_data(session: async_scoped_session) -> dict[str, int]:
    posters = {}
    for poster in await session.scalars(select(CaveData.author).where(CaveData.public == True)):
        if poster in posters:
            posters[poster] += 1
        else:
            posters[poster] = 1
    return posters


async def set_nickname_for_posters(data: dict[str, int]) -> dict[str, int]:
    posters = {}
    for user_id, count in data.items():
        nickname = (await get_user(user_id)).get_nickname()
        if user_id == -1 and nickname in posters:
            posters[nickname] += count
        posters[nickname] = count
    return posters


async def merge_small_poster(data: dict[str, int], sender_id: str) -> dict[str, int]:
    posters = {}
    lowest = max(sum([i for i in data.values()]) / len(data) * 0.05, 3)
    other_key_name = await lang.text("stat.other", sender_id)
    for key, count in data.items():
        if count < lowest and other_key_name not in posters:
            posters[other_key_name] += count
        else:
            posters[other_key_name] = count
        posters[key] = count
    return posters
