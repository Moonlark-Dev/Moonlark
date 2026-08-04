from datetime import datetime, timedelta
from typing import Any, Literal

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, At, Match, Subcommand, UniMessage, on_alconna
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larkuser import get_nickname, get_user, patch_matcher
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_ranking.types import RankingData
from nonebot_plugin_render import render_template
from sqlalchemy import Row, func, select

from .lang import lang
from .models import AttackRecord
from .utils import NotEnoughEggs, deduct_eggs

EGG_ID = "moonlark:egg"
DAMAGE_PER_EGG = 0.2
SpanType = Literal["7d", "30d", "total"]

alc = Alconna(
    "splat",
    Subcommand("rank", Args["span", SpanType, "total"]),
    Subcommand("throwers", Args["span", SpanType, "total"]),
    Subcommand("info", Args["target?", At]),
    Args["target?", At]["count?", int],
)
splat = on_alconna(alc)
patch_matcher(splat)


def get_start_datetime(span: str) -> datetime | None:
    if span == "7d":
        return datetime.now() - timedelta(days=7)
    if span == "30d":
        return datetime.now() - timedelta(days=30)
    return None


async def build_ranking(column: Any, span: str) -> list[Row]:
    total = func.sum(AttackRecord.count).label("total_count")
    stmt = select(column, total).group_by(column).order_by(total.desc())
    start = get_start_datetime(span)
    if start is not None:
        stmt = stmt.where(AttackRecord.time >= start)
    async with get_session() as session:
        return list((await session.execute(stmt)).all())


async def sum_count(column: Any, value: str, start: datetime | None) -> int:
    stmt = select(func.sum(AttackRecord.count)).where(column == value)
    if start is not None:
        stmt = stmt.where(AttackRecord.time >= start)
    async with get_session() as session:
        return (await session.scalar(stmt)) or 0


async def max_count(column: Any, value: str, start: datetime | None) -> int:
    stmt = select(func.max(AttackRecord.count)).where(column == value)
    if start is not None:
        stmt = stmt.where(AttackRecord.time >= start)
    async with get_session() as session:
        return (await session.scalar(stmt)) or 0


async def get_span_text(span: str, user_id: str) -> str:
    return await lang.text(f"span_{span}", user_id)


@splat.assign("$main")
async def throw_egg(
    bot: Bot,
    event: Event,
    target: Match[At],
    count: Match[int],
    user_id: str = get_user_id(),
) -> None:
    if not target.available:
        await lang.finish("throw.usage", user_id)
    egg_count = count.result if count.available else 1
    if egg_count <= 0:
        await lang.finish("throw.invalid_count", user_id)
    target_id = target.result.target

    egg_location = get_location_by_id(EGG_ID)
    async with get_session() as session:
        try:
            await deduct_eggs(session, user_id, egg_location, egg_count)
        except NotEnoughEggs as e:
            await session.rollback()
            await lang.finish("throw.not_enough", user_id, e.have)
        session.add(
            AttackRecord(
                user_id=user_id,
                target_id=target_id,
                count=egg_count,
                egg_id=EGG_ID,
                time=datetime.now(),
            ),
        )
        await session.commit()

    target_user = await get_user(target_id)
    hp_lost = 0
    if target_user.is_registered():
        before_hp = target_user.get_health()
        await target_user.damage(egg_count * DAMAGE_PER_EGG)
        hp_lost = round(before_hp - target_user.get_health(), 1)

    nickname = await get_nickname(target_id, bot, event)
    if hp_lost > 0:
        await lang.finish("throw.success_damage", user_id, nickname, egg_count, hp_lost)
    if target_user.is_registered():
        await lang.finish("throw.success", user_id, nickname, egg_count)
    await lang.finish("throw.success_unregistered", user_id, nickname, egg_count)


@splat.assign("rank")
async def rank(span: SpanType = "total", user_id: str = get_user_id()) -> None:
    rows = await build_ranking(AttackRecord.target_id, span)
    if not rows:
        await lang.finish("rank.no_data", user_id)
    span_text = await get_span_text(span, user_id)
    ranked_data = [RankingData(user_id=row.target_id, data=row.total_count, info=None) for row in rows]
    # TODO 兼容 WebRanking
    title = await lang.text("rank.title", user_id, span_text)
    image = await generate_image(ranked_data, user_id, title)
    await splat.finish(await UniMessage().image(raw=image, name="image.png").export())


@splat.assign("throwers")
async def throwers(span: SpanType = "total", user_id: str = get_user_id()) -> None:
    rows = await build_ranking(AttackRecord.user_id, span)
    if not rows:
        await lang.finish("throwers.no_data", user_id)
    span_text = await get_span_text(span, user_id)
    # ranked_data = [{"user_id": row.user_id, "data": row.total_count, "info": None} for row in rows]
    ranked_data = [RankingData(user_id=row.user_id, data=row.total_count, info=None) for row in rows]
    title = await lang.text("throwers.title", user_id, span_text)
    image = await generate_image(ranked_data, user_id, title)
    await splat.finish(await UniMessage().image(raw=image, name="image.png").export())


@splat.assign("info")
async def info(bot: Bot, event: Event, target: Match[At], user_id: str = get_user_id()) -> None:
    target_id = target.result.target if target.available else user_id
    data = {}
    for span in ("7d", "30d", "total"):
        start = get_start_datetime(span)
        data[span] = {
            "received": await sum_count(AttackRecord.target_id, target_id, start),
            "thrown": await sum_count(AttackRecord.user_id, target_id, start),
            "max_attack": await max_count(AttackRecord.user_id, target_id, start),
            "max_received": await max_count(AttackRecord.target_id, target_id, start),
        }
    nickname = await get_nickname(target_id, bot, event)
    image = await render_template(
        "splat_info.html.jinja",
        await lang.text("info.title", user_id),
        user_id,
        {
            "data": data,
            "nickname": nickname,
            "target_id": target_id,
            "text": {
                "received": await lang.text("info.text.received", user_id),
                "thrown": await lang.text("info.text.thrown", user_id),
                "max_attack": await lang.text("info.text.max_attack", user_id),
                "max_received": await lang.text("info.text.max_received", user_id),
                "span_7d": await lang.text("span_7d", user_id),
                "span_30d": await lang.text("span_30d", user_id),
                "span_total": await lang.text("span_total", user_id),
            },
        },
    )
    await splat.finish(await UniMessage().image(raw=image, name="image.png").export())
