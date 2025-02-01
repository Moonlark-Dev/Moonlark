from datetime import date
import json
from pathlib import Path
from typing import Optional, TypedDict
import aiofiles
from nonebot_plugin_orm import async_scoped_session, AsyncSession, get_session
from sqlalchemy import select
from nonebot_plugin_items.types import DictItemData
from .models import UserSchedule


async def get_schedule_status(
    user_id: str, schedule_id: str, session: async_scoped_session | AsyncSession
) -> Optional[UserSchedule]:
    return await session.scalar(
        select(UserSchedule).where(
            UserSchedule.user_id == user_id,
            UserSchedule.task_id == schedule_id,
            UserSchedule.updated_at == date.today(),
        )
    )


class DictUserScheduleStatus(TypedDict):
    completed_count: int
    collected: bool


class ScheduleConfig(TypedDict):
    award: list[DictItemData]
    completion_required: int


def schedule_model_to_dict(model: Optional[UserSchedule]) -> Optional[DictUserScheduleStatus]:
    if model:
        return {
            "collected": model.collected,
            "completed_count": model.completed_count,
        }


async def get_schedule_list() -> dict[str, ScheduleConfig]:
    async with aiofiles.open(Path(__file__).parent.joinpath("schedule.json"), "r", encoding="utf-8") as f:
        return json.loads(await f.read())


async def complete_schedule(user_id: str, task_id: str, count: int = 1) -> None:
    async with get_session() as session:
        result = await get_schedule_status(user_id, task_id, session)
        if result is None:
            result = UserSchedule(user_id=user_id, task_id=task_id, updated_at=date.today(), completed_count=0)
        result.completed_count += count
        await session.merge(result)
        await session.commit()
