import asyncio
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_localstore import get_data_file
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from nonebot import get_driver, logger

import aiofiles
import json
import time
import math
import traceback

from ...nonebot_plugin_email.utils.send import send_email

from ..__main__ import lang
from ..types import JsonCycleData, LEVEL
from ..models import QuickMathUser

cycle_data_file = get_data_file("nonebot_plugin_quick_math", "cycle.json")


async def get_cycle_data() -> JsonCycleData:
    try:
        async with aiofiles.open(cycle_data_file, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except Exception:
        logger.error(f"读取 cycle.json 时出现错误: {traceback.format_exc()}")
        return {"number": 1, "start_time": int(time.time() // 86400 * 86400)}


@get_driver().on_startup
async def init() -> None:
    if not cycle_data_file.exists():
        data = await get_cycle_data()
        async with aiofiles.open(cycle_data_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data))


async def get_remain() -> tuple[int, float]:
    data = await get_cycle_data()
    remain = data["start_time"] + 86400 - time.time()
    remain_hours = int(remain // 3600)
    remain_mins = round((remain - remain_hours * 3600) / 60, 2)
    return remain_hours, remain_mins


def get_cycle_point(max_point: int, use_count: int) -> float:
    return round(max_point + (math.log(use_count + 0.1) + 1) * 7, 3)


LEVELS = ["A", "B", "C", "D"]


async def get_user_level(rank: int) -> LEVEL:
    async with get_session() as session:
        total = len((await session.scalars(select(QuickMathUser).where(QuickMathUser.use_count_this_cycle != 0))).all())
    if rank <= total * 0.25:
        return "A"
    elif rank <= total * 0.5:
        return "B"
    elif rank <= total * 0.75:
        return "C"
    else:
        return "D"


async def get_rank(point: float) -> int:
    count = 1
    async with get_session() as session:
        for user in await session.scalars(select(QuickMathUser).where(QuickMathUser.use_count_this_cycle > 0)):
            if point < get_cycle_point(user.max_point_this_cycle, user.use_count_this_cycle):
                count += 1
    return count


async def get_user_point(user_id: str) -> float:
    async with get_session() as session:
        user = await session.get(QuickMathUser, user_id)
        if user is None:
            await lang.finish("award.none", user_id)
            raise
        point = get_cycle_point(user.max_point_this_cycle, user.use_count_this_cycle)
    return point


async def get_award_pawcoin(point: float, level_string: str) -> int:
    level = LEVELS[::-1].index(level_string) + 1
    return round(math.sqrt(1 + point // 100) * level)


async def start_new_cycle() -> None:
    async with aiofiles.open(cycle_data_file, "r+", encoding="utf-8") as f:
        data = await f.read()
        data = json.loads(data)
        data["number"] += 1
        data["start_time"] = int(time.time() // 86400 * 86400)
        await f.seek(0)
        await f.write(json.dumps(data))


@scheduler.scheduled_job("cron", hour="0", id="settlement_quick_math")
async def _() -> None:
    cycle = await get_cycle_data()
    async with get_session() as session:
        for user in await session.scalars(select(QuickMathUser).where(QuickMathUser.use_count_this_cycle != 0)):
            point = await get_user_point(user.user_id)
            rank = await get_rank(point)
            level = await get_user_level(rank)
            award_pawcoin = await get_award_pawcoin(point, level)
            award_exp = 4 * (LEVELS[::-1].index(level) + 1)
            await send_email(
                [user.user_id],
                await lang.text("award_email.subject", user.user_id),
                await lang.text("award_email.body", user.user_id, cycle["number"], point, rank, level),
                items=[
                    {"item_id": "moonlark:pawcoin", "count": award_pawcoin, "data": {}},
                    {"item_id": "special:experience", "count": award_exp, "data": {}},
                ],
            )
            user.max_point_this_cycle = 0
            user.use_count_this_cycle = 0
        await session.commit()
    await start_new_cycle()
