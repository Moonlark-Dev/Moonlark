from datetime import datetime, timedelta
from typing import Any, Literal

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, At, Match, Option, Subcommand, UniMessage, on_alconna
from nonebot_plugin_buff import BAD_LUCK_BUFF_ID, attach_buff
from nonebot_plugin_equip import BarrierResult, handle_barrier
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larkuser import get_nickname, get_user, patch_matcher
from nonebot_plugin_larkutils import get_main_account, get_user_id
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_ranking.types import RankingData
from nonebot_plugin_render import render_template
from nonebot_plugin_shop.utils import offer_purchase_when_short
from sqlalchemy import Row, func, select

from .lang import lang
from .models import AttackRecord
from .utils import (
    EGG_TYPES,
    EggTypeData,
    NotEnoughEggs,
    ROTTEN_EGG_EX_TYPE,
    deduct_eggs,
    get_egg_count,
    get_egg_type_name,
    get_moonlark_user_ids,
    get_selected_egg_type,
    resolve_egg_type,
    roll_hand_explosion,
    set_selected_egg_type,
)

SpanType = Literal["7d", "30d", "total"]

alc = Alconna(
    "splat",
    Subcommand("eggs"),
    Subcommand("rank", Args["span", SpanType, "total"]),
    Subcommand("throwers", Args["span", SpanType, "total"]),
    Subcommand("info", Args["target?", At]),
    Subcommand("switch", Args["index", int]),
    Args["target?", At]["count?", int],
    Option("--type|-t", Args["egg_type", str]),
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


async def throw_eggs(
    user_id: str, target_id: str, egg_key: str, count: int, bot: Bot, record_count: int | None = None
) -> int | None:
    """扣除鸡蛋并写入攻击记录。

    鸡蛋不足且商店有售时，先询问是否购买缺口再重试一次；
    成功返回 None，仍然不足时返回当前持有数量供调用方提示。

    Args:
        count: 需要扣除的鸡蛋数量
        record_count: 攻击记录中登记的数量（例如手上爆炸的鸡蛋不会飞出去；None 时与 count 一致）
    """
    egg_item_id = EGG_TYPES[egg_key].item_id
    egg_location = get_location_by_id(egg_item_id)
    await offer_purchase_when_short(user_id, egg_item_id, count, bot)

    async with get_session() as session:
        try:
            await deduct_eggs(session, user_id, egg_location, count)
        except NotEnoughEggs as error:
            await session.rollback()
            return error.have
        if record_count is None or record_count > 0:
            session.add(
                AttackRecord(
                    user_id=user_id,
                    target_id=target_id,
                    count=record_count if record_count is not None else count,
                    egg_id=egg_item_id,
                    time=datetime.now(),
                ),
            )
        await session.commit()
    return None


async def apply_egg_hit(victim_id: str, egg_type: EggTypeData, count: int) -> float:
    """鸡蛋命中某人：扣血并附着霉运 buff（伤害与霉运时长由鸡蛋种类决定）

    Returns:
        实际扣除的 HP（未注册的扣 0）
    """
    if count <= 0:
        return 0.0
    hp_lost = 0.0
    victim = await get_user(victim_id)
    if victim.is_registered():
        before_hp = victim.get_health()
        await victim.damage(round(count * egg_type.damage, 1))
        hp_lost = round(before_hp - victim.get_health(), 1)
    if egg_type.buff_hours > 0:
        await attach_buff(
            await get_main_account(victim_id),
            BAD_LUCK_BUFF_ID,
            duration=timedelta(hours=egg_type.buff_hours),
            layers=count,
        )
    return hp_lost


@splat.assign("$main")
async def throw_egg(
    bot: Bot,
    event: Event,
    target: Match[At],
    count: Match[int],
    egg_type: Match[str],
    user_id: str = get_user_id(),
) -> None:
    if not target.available:
        # /splat 不带参数：展示当前选择的鸡蛋种类和所有可用种类（类似 /present）
        await show_egg_types(user_id)
        return

    egg_count = count.result if count.available else 1
    if egg_count <= 0:
        await lang.finish("throw.invalid_count", user_id)

    # 解析鸡蛋种类：-t/--type 优先（只影响本次，不修改默认选择），否则使用已保存的选择
    if egg_type.available:
        egg_key = resolve_egg_type(egg_type.result)
        if egg_key is None:
            await lang.finish("throw.invalid_type", user_id, egg_type.result, len(EGG_TYPES), "、".join(EGG_TYPES))
    else:
        egg_key = await get_selected_egg_type(user_id)

    target_id = target.result.target
    egg_data = EGG_TYPES[egg_key]
    egg_name = await get_egg_type_name(egg_key, user_id)

    # 每个鸡蛋都有概率在手上爆炸（爆炸相当于砸自己）；爆炸的鸡蛋不会飞出去
    exploded = roll_hand_explosion(egg_key, egg_count)
    flight_count = egg_count - exploded

    # 鸡蛋不足时先询问是否购买缺口，购买后重试（重试结果由 throw_eggs 判定）
    if (have := await throw_eggs(user_id, target_id, egg_key, egg_count, bot, flight_count)) is not None:
        await lang.finish("throw.not_enough", user_id, egg_name, have)

    lines = []

    # 反弹与屏障：Moonlark 自己会反弹所有鸡蛋；装备了临时屏障的用户也会（有概率）反弹
    reflected_self_damage = 0.0
    reflect_reason: str | None = None
    if flight_count > 0 and target_id in get_moonlark_user_ids():
        reflect_reason = "reflect"
    barrier_result: BarrierResult | None = None
    if flight_count > 0 and reflect_reason is None:
        barrier_result = await handle_barrier(target_id, egg_key == ROTTEN_EGG_EX_TYPE)
        if barrier_result.blocked and barrier_result.reflected:
            reflect_reason = "barrier_reflect"

    if flight_count > 0:
        if reflect_reason == "reflect":
            reflected_self_damage = await apply_egg_hit(user_id, egg_data, flight_count)
            lines.append(await lang.text("throw.reflect", user_id, flight_count, egg_name, reflected_self_damage))
        elif reflect_reason == "barrier_reflect":
            reflected_self_damage = await apply_egg_hit(user_id, egg_data, flight_count)
            lines.append(
                await lang.text("throw.barrier_reflect", user_id, flight_count, egg_name, reflected_self_damage)
            )
        elif barrier_result is not None and barrier_result.blocked:
            blocks_text = (
                await lang.text("throw.blocked_broken", user_id)
                if barrier_result.destroyed
                else await lang.text("throw.blocked_remaining", user_id, barrier_result.remaining)
            )
            lines.append(await lang.text("throw.blocked", user_id, flight_count, egg_name, blocks_text))
        else:
            hp_lost = await apply_egg_hit(target_id, egg_data, flight_count)
            nickname = await get_nickname(target_id, bot, event)
            if barrier_result is not None and barrier_result.pierced:
                lines.append(await lang.text("throw.pierced", user_id, egg_name))
            if hp_lost > 0:
                lines.append(
                    await lang.text("throw.success_damage", user_id, nickname, flight_count, egg_name, hp_lost)
                )
            elif (await get_user(target_id)).is_registered():
                lines.append(await lang.text("throw.success", user_id, nickname, flight_count, egg_name))
            else:
                lines.append(await lang.text("throw.success_unregistered", user_id, nickname, flight_count, egg_name))

    if exploded > 0:
        explode_damage = await apply_egg_hit(user_id, egg_data, exploded)
        lines.append(await lang.text("throw.explode_hand", user_id, exploded, egg_name, explode_damage))

    await splat.finish("\n".join(lines))


async def show_egg_types(user_id: str) -> None:
    """展示当前选择的鸡蛋种类和所有可用种类（类似 /present）"""
    current = await get_selected_egg_type(user_id)
    current_name = await get_egg_type_name(current, user_id)
    lines = [await lang.text("list.title", user_id, current_name)]
    for index, egg_key in enumerate(EGG_TYPES, start=1):
        egg_data = EGG_TYPES[egg_key]
        name = await get_egg_type_name(egg_key, user_id)
        if egg_data.buff_hours > 0:
            lines.append(
                await lang.text(
                    "list.item_buff",
                    user_id,
                    index,
                    name,
                    egg_data.damage,
                    egg_data.buff_hours,
                    round(egg_data.explode_chance * 100, 1),
                )
            )
        else:
            lines.append(await lang.text("list.item", user_id, index, name, egg_data.damage))
    lines.append(await lang.text("list.footer", user_id))
    await splat.finish("\n".join(lines))


@splat.assign("switch")
async def switch_egg(index: int, user_id: str = get_user_id()) -> None:
    keys = list(EGG_TYPES)
    if not 1 <= index <= len(keys):
        await lang.finish("switch.invalid_index", user_id, len(keys))
    egg_key = keys[index - 1]
    await set_selected_egg_type(user_id, egg_key)
    name = await get_egg_type_name(egg_key, user_id)
    await lang.finish("switch.success", user_id, name)


async def build_eggs_markdown(user_id: str, clickable: bool) -> str:
    """构建鸡蛋列表的 markdown：每种鸡蛋展示持有数量与效果。

    Args:
        clickable: QQ 平台为 True 时把鸡蛋名渲染成可点击切换的 <qqbot-cmd-input>
    """
    current = await get_selected_egg_type(user_id)
    lines = []
    for index, (egg_key, egg_data) in enumerate(EGG_TYPES.items(), start=1):
        name = await get_egg_type_name(egg_key, user_id)
        count = await get_egg_count(user_id, get_location_by_id(egg_data.item_id))
        count_text = f"x{count}"
        if egg_key == current:
            count_text += await lang.text("eggs.current", user_id)
        if clickable:
            lines.append(await lang.text("eggs.item", user_id, index, name, count_text))
        else:
            lines.append(await lang.text("eggs.item_plain", user_id, name, count_text))
        if egg_data.buff_hours > 0:
            effect = await lang.text(
                "eggs.effect_buff",
                user_id,
                egg_data.damage,
                egg_data.buff_hours,
                round(egg_data.explode_chance * 100, 1),
            )
        else:
            effect = await lang.text("eggs.effect_plain", user_id, egg_data.damage)
        lines.append(f"> {effect}")
    title = await lang.text("eggs.title", user_id, await get_egg_type_name(current, user_id))
    return "\n".join([title, *lines])


@splat.assign("eggs")
async def show_eggs(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    """展示每种鸡蛋的持有数量与效果"""
    if isinstance(bot, QQBot):
        await (
            UniMessage()
            .style(await build_eggs_markdown(user_id, clickable=True), "markdown")
            .send(target=event, bot=bot)
        )
        await splat.finish()
    await splat.finish(
        await UniMessage().image(raw=await md_to_pic(await build_eggs_markdown(user_id, clickable=False))).export()
    )


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
                "received": await lang.text("info.data.received", user_id),
                "thrown": await lang.text("info.data.thrown", user_id),
                "max_attack": await lang.text("info.data.max_attack", user_id),
                "max_received": await lang.text("info.data.max_received", user_id),
                "span_7d": await lang.text("span_7d", user_id),
                "span_30d": await lang.text("span_30d", user_id),
                "span_total": await lang.text("span_total", user_id),
            },
        },
    )
    await splat.finish(await UniMessage().image(raw=image, name="image.png").export())
