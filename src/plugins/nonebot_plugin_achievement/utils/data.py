from pathlib import Path
from typing import AsyncGenerator, Optional
from nonebot.compat import type_validate_json
import aiofiles
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..types import AchievementUnlockData, UserAchievementData
from nonebot.log import logger
from ...nonebot_plugin_larklang.__main__ import LangHelper

from ..models import AchievementList, User
from ...nonebot_plugin_item.registry.registry import ResourceLocation


async def get_achievement_list(namespace: Optional[str] = None) -> AsyncGenerator[ResourceLocation, None]:
    for file in Path(__file__).parent.parent.joinpath("achievements").iterdir():
        if namespace and file.name[:-5] != namespace or not file.name.endswith(".json"):
            continue
        async with aiofiles.open(file, encoding="utf-8") as f:
            data = type_validate_json(AchievementList, await f.read())
        for achievement in data.achievements.keys():
            yield ResourceLocation(file.name[:-5], achievement)


async def get_achievement_data(id_: ResourceLocation) -> AchievementList:
    file = Path(__file__).parent.parent.joinpath(f"achievements/{id_.getNamespace()}.json")
    async with aiofiles.open(file, encoding="utf-8") as f:
        data = type_validate_json(AchievementList, await f.read())
    data.achievements = {id_.getPath(): data.achievements[id_.getPath()]}
    return data


async def is_achievement_unlocked(id_: ResourceLocation, count: int) -> bool:
    data = (await get_achievement_data(id_)).achievements[id_.getPath()]
    logger.debug(f"成就 {id_.getItemID()} 需要的解锁次数为: {data.required_unlock_count} ({count=})")
    return count >= data.required_unlock_count


async def get_achievement_name(id_: ResourceLocation, user_id: str) -> str:
    data = await get_achievement_data(id_)
    path = id_.getPath()
    return await LangHelper(data.lang.plugin).text(f"{data.lang.key}.{data.achievements[path].key or path}", user_id)


async def get_achievement_description(id_: ResourceLocation, user_id: str) -> Optional[str]:
    data = await get_achievement_data(id_)
    achievement_id = data.achievements[id_.getPath()].key or id_.getPath()
    if not data.achievements[achievement_id]:
        return None
    return await LangHelper(data.lang.plugin).text(f"{data.lang.key}.{achievement_id}_description", user_id)


async def get_unlock_status(id_: ResourceLocation, user_id: str) -> AchievementUnlockData:
    async with get_session() as session:
        data = await session.scalar(
            select(User).where(
                User.user_id == user_id,
                User.achievement_namespace == id_.getNamespace(),
                User.achievement_path == id_.getPath(),
            )
        )
        if data is None:
            return {
                "progress": 0,
                "unlocked": False,
            }
        return {
            "progress": data.unlock_progress,
            "unlocked": data.unlocked,
        }


async def get_user_achievement(id_: ResourceLocation, user_id: str) -> UserAchievementData:
    return {
        "user_id": user_id,
        "achievement": (await get_achievement_data(id_)).achievements[id_.getPath()],
        "name": await get_achievement_name(id_, user_id),
        "description": await get_achievement_description(id_, user_id),
        "unlock": await get_unlock_status(id_, user_id),
    }
