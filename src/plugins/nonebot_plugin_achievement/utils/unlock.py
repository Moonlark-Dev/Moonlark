from nonebot_plugin_orm import get_session
from nonebot.log import logger
from sqlalchemy import select

from nonebot_plugin_email.utils.send import send_email
from .data import get_achievement_data, get_achievement_name, is_achievement_unlocked
from ..models import User
from nonebot_plugin_items.registry.registry import ResourceLocation
from ..__main__ import lang


async def on_achievement_unlock(id_: ResourceLocation, user_id: str) -> None:
    logger.info(f"用户 {user_id} 解锁成就 {id_.getPath()}")
    items = (await get_achievement_data(id_)).achievements[id_.getPath()].awards
    await send_email(
        [user_id],
        await lang.text("unlock_email.subject", user_id),
        await lang.text("unlock_email.content", user_id, await get_achievement_name(id_, user_id)),
        items=items,
    )


async def unlock_achievement(id_: ResourceLocation, user_id: str, count: int = 1) -> None:
    async with get_session() as session:
        data = await session.scalar(
            select(User).where(
                User.user_id == user_id,
                User.achievement_namespace == id_.getNamespace(),
                User.achievement_path == id_.getPath(),
            )
        )
        if data is None:
            if await is_achievement_unlocked(id_, count):
                await on_achievement_unlock(id_, user_id)
                unlocked = True
            else:
                unlocked = False
            session.add(
                User(
                    user_id=user_id,
                    achievement_namespace=id_.getNamespace(),
                    achievement_path=id_.getPath(),
                    unlock_progress=count,
                    unlocked=unlocked,
                )
            )
        elif data.unlocked:
            return
        else:
            data.unlock_progress += count
            if await is_achievement_unlocked(id_, data.unlock_progress) and not data.unlocked:
                await on_achievement_unlock(id_, user_id)
                data.unlocked = True
        await session.commit()
