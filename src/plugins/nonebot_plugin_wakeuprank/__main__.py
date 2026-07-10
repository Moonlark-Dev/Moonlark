from datetime import date, datetime, time, timedelta

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Alconna, Subcommand, UniMessage, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_last_seen.models import LastSeenRecord
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_ranking.types import RankingData
from nonebot_plugin_render.render import render_template
from sqlalchemy import delete, func, select

from .lang import lang
from .models import RiseData

GLOBAL_SESSION_ID = "global"
WAKE_START = time(4, 0, 0)
WAKE_END = time(14, 0, 0)

recorder = on_message(block=False, priority=90)


@recorder.handle()
async def _(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    now = datetime.now()
    current_time = now.time()
    if not (WAKE_START <= current_time < WAKE_END):
        return

    today = now.date()
    async with get_session() as session:
        result = await session.scalar(
            select(RiseData).where(RiseData.user_id == user_id, RiseData.record_date == today),
        )
        if result is not None:
            return

        last_seen = await session.scalar(
            select(LastSeenRecord.last_seen).where(
                LastSeenRecord.user_id == user_id,
                LastSeenRecord.session_id == GLOBAL_SESSION_ID,
            ),
        )
        if last_seen is None:
            valid = True
        else:
            delta = now - last_seen
            valid = delta > timedelta(hours=1)

        record = RiseData(user_id=user_id, record_date=today, wake_time=now, valid=valid)
        session.add(record)
        await session.commit()


@scheduler.scheduled_job("cron", hour=4, minute=0, id="wakeuprank_cleanup")
async def cleanup_invalid_records() -> None:
    async with get_session() as session:
        await session.execute(delete(RiseData).where(RiseData.valid == False))  # noqa: E712
        await session.commit()


wakeuprank_alc = Alconna(
    "wakeuprank",
    Subcommand("avg"),
    Subcommand("today"),
)
wakeuprank = on_alconna(wakeuprank_alc)


async def _fmt_time(avg_seconds: float) -> str:
    total = max(0, int(avg_seconds)) + 14400
    h = (total // 3600) % 24
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


async def _get_user_valid_records(session, user_id: str):
    result = await session.execute(
        select(RiseData.wake_time, RiseData.record_date).where(
            RiseData.user_id == user_id, RiseData.valid == True
        )  # noqa: E712
    )
    return result.all()


@wakeuprank.assign("$main")
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        subq = (
            select(
                RiseData.user_id,
                RiseData.record_date,
                RiseData.wake_time,
                func.row_number()
                .over(partition_by=RiseData.record_date, order_by=[RiseData.wake_time, RiseData.user_id])
                .label("rn"),
            ).where(
                RiseData.valid == True
            )  # noqa: E712
        ).subquery()

        winners = (
            await session.execute(
                select(subq.c.user_id, subq.c.record_date, subq.c.wake_time).where(subq.c.rn == 1),
            )
        ).all()
    if not winners:
        await lang.finish("wakeuprank.no_data", user_id)

    user_counts: dict[str, int] = {}
    for row in winners:
        uid = row[0]
        user_counts[uid] = user_counts.get(uid, 0) + 1

    sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)

    async with get_session() as session:
        ranked_data: list[RankingData] = []
        for uid, count in sorted_users:
            rows = await _get_user_valid_records(session, uid)
            if rows:
                offsets = [(wt - datetime.combine(d, WAKE_START)).total_seconds() for wt, d in rows]
                avg_offset = sum(offsets) / len(offsets)
                avg_time_str = await _fmt_time(avg_offset)
            else:
                avg_time_str = "00:00:00"
            ranked_data.append({"user_id": uid, "data": count, "info": avg_time_str})

    title = await lang.text("wakeuprank.title", user_id)
    image = await generate_image(ranked_data, user_id, title)
    await wakeuprank.finish(await UniMessage().image(raw=image, name="image.png").export())


@wakeuprank.assign("avg")
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        rows = (
            await session.execute(
                select(RiseData.user_id, RiseData.record_date, RiseData.wake_time).where(
                    RiseData.valid == True
                )  # noqa: E712
            )
        ).all()
    if not rows:
        await lang.finish("wakeuprank.no_data", user_id)

    user_times: dict[str, list[float]] = {}
    for row in rows:
        uid = row[0]
        d = row[1]
        wt = row[2]
        offset = (wt - datetime.combine(d, WAKE_START)).total_seconds()
        if uid not in user_times:
            user_times[uid] = []
        user_times[uid].append(offset)

    user_avg: dict[str, float] = {uid: sum(offsets) / len(offsets) for uid, offsets in user_times.items()}
    sorted_users = sorted(user_avg.items(), key=lambda x: x[1])

    ranked_data: list[RankingData] = [
        {"user_id": uid, "data": round(avg_seconds), "info": await _fmt_time(avg_seconds)}
        for uid, avg_seconds in sorted_users
    ]

    title = await lang.text("wakeuprank.avg_title", user_id)
    image = await render_template(
        "wakeuprank_avg.html.jinja",
        title,
        user_id,
        {
            "me": None,
            "users": [
                {
                    "nickname": (await get_user(item["user_id"])).get_nickname(),
                    "info": item["info"],
                    "seconds": item["data"],
                }
                for item in ranked_data[:7]
            ],
        },
    )
    await wakeuprank.finish(await UniMessage().image(raw=image, name="image.png").export())


@wakeuprank.assign("today")
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    today = date.today()
    async with get_session() as session:
        rows = (
            (
                await session.execute(
                    select(RiseData)
                    .where(RiseData.record_date == today, RiseData.valid == True)  # noqa: E712
                    .order_by(RiseData.wake_time),
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        await lang.finish("wakeuprank.no_data", user_id)

    ranked_data: list[RankingData] = [
        {
            "user_id": row.user_id,
            "data": int((row.wake_time - datetime.combine(today, WAKE_START)).total_seconds()),
            "info": row.wake_time.strftime("%H:%M:%S"),
        }
        for row in rows
    ]

    title = await lang.text("wakeuprank.today_title", user_id)
    image = await generate_image(ranked_data, user_id, title)
    await wakeuprank.finish(await UniMessage().image(raw=image, name="image.png").export())
