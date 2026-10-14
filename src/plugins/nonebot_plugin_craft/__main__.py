from datetime import datetime

from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Button, Subcommand, UniMessage, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkuser.utils.waiter import PromptRetryTooMuch, PromptTimeout, prompt
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import get_session

from sqlalchemy import select

from .lang import lang
from .models import CraftingJob
from .recipes import LEVEL_SLOTS, MAX_LEVEL, RECIPES
from .utils import (
    NoFreeSlot,
    NotEnoughMaterial,
    NotEnoughVimcoin,
    collect_finished_jobs,
    format_remaining,
    get_item_name,
    get_machine,
    get_running_jobs,
    get_slots_info,
    get_upgrade_cost,
    start_job,
    try_upgrade,
)

# 升级确认中允许的回复，以及被视为「同意升级」的回复
ANSWER_ALIASES = {"y", "yes", "n", "no"}
AGREE_ANSWERS = {"y", "yes"}

alc = Alconna(
    "craft",
    Subcommand("start", Args["recipe_id", str], Args["count", int, 1]),
    Subcommand("collect"),
    Subcommand("upgrade"),
    Args["recipe_id?", str],
)
craft = on_alconna(alc)
patch_matcher(craft)


def format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{minutes} 分钟"


async def _render_recipe_line(recipe, user_id: str) -> str:
    inputs = "、".join(f"{await get_item_name(item_id, user_id)}x{count}" for item_id, count in recipe.inputs.items())
    output_name = await get_item_name(recipe.output_id, user_id)
    return await lang.text(
        "recipe.item",
        user_id,
        recipe.id,
        output_name,
        recipe.output_count,
        inputs,
        recipe.vimcoin,
        format_duration(recipe.duration.total_seconds()),
    )


async def _maybe_collect(user_id: str) -> tuple[str, str]:
    """收集已完成的任务，返回 (收集文本, 产物文本)"""
    deliveries = await collect_finished_jobs(user_id)
    if not deliveries:
        return "", ""
    delivered = "、".join(f"{await get_item_name(recipe.output_id, user_id)}x{count}" for recipe, count in deliveries)
    return await lang.text("list.collected", user_id, delivered), delivered


@craft.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    machine = await get_machine(user_id)
    total, used = await get_slots_info(user_id)
    lines = [
        await lang.text("list.title", user_id, machine.level, total),
        await lang.text("list.slots", user_id, used, total),
    ]
    upgrade_cost = get_upgrade_cost(machine.level)
    if upgrade_cost is not None:
        lines.append(
            await lang.text("list.upgrade", user_id, upgrade_cost, machine.level + 1, LEVEL_SLOTS[machine.level + 1])
        )
    else:
        lines.append(await lang.text("list.upgrade_max", user_id, MAX_LEVEL))

    collected_text, delivered = await _maybe_collect(user_id)
    if delivered:
        lines.append(collected_text)

    jobs = await get_running_jobs(user_id)
    if jobs:
        lines.append(await lang.text("list.jobs_title", user_id))
        for job in jobs:
            recipe = RECIPES.get(job.recipe_id)
            name = await get_item_name(recipe.output_id, user_id) if recipe else job.recipe_id
            lines.append(await lang.text("list.job", user_id, name, format_remaining(job.finish_time)))
    else:
        lines.append(await lang.text("list.jobs_empty", user_id, total - used, total))
    if RECIPES:
        lines.append(await lang.text("recipe.title", user_id))
        for recipe in RECIPES.values():
            lines.append(await _render_recipe_line(recipe, user_id))
    lines.append(await lang.text("list.footer", user_id))
    await craft.finish("\n".join(lines))


@craft.assign("start")
async def _(recipe_id: str, count: int = 1, user_id: str = get_user_id()) -> None:
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        await lang.finish("start.invalid_recipe", user_id, recipe_id)
    if count <= 0:
        await lang.finish("start.invalid_count", user_id)

    started = 0
    finish_time: datetime | None = None
    for _ in range(count):
        try:
            job = await start_job(user_id, recipe)
        except NoFreeSlot as error:
            if started:
                break
            await lang.finish("start.no_slot", user_id, error.free)
        except NotEnoughMaterial as error:
            if started:
                break
            material_name = await get_item_name(error.item_id, user_id)
            await lang.finish("start.not_enough_material", user_id, material_name, error.need, error.have)
        except NotEnoughVimcoin as error:
            if started:
                break
            await lang.finish("start.not_enough_vimcoin", user_id, error.need, error.have)
        started += 1
        finish_time = job.finish_time
    name = await get_item_name(recipe.output_id, user_id)
    await lang.finish("start.started", user_id, name, started, format_remaining(finish_time))


@craft.assign("collect")
async def _(user_id: str = get_user_id()) -> None:
    deliveries = await collect_finished_jobs(user_id)
    if not deliveries:
        await lang.finish("collect.done", user_id)
    delivered = "、".join(f"{await get_item_name(recipe.output_id, user_id)}x{count}" for recipe, count in deliveries)
    await lang.finish("collect.success", user_id, delivered)


@craft.assign("upgrade")
async def _(bot: Bot, user_id: str = get_user_id()) -> None:
    """升级合成机：先弹出确认（QQ 官方机器人使用键盘按钮回复），确认后扣费升级"""
    machine = await get_machine(user_id)
    cost = get_upgrade_cost(machine.level)
    if cost is None:
        await lang.finish("upgrade.maxed", user_id)
    next_slots = LEVEL_SLOTS[machine.level + 1]

    prompt_data: str | UniMessage = await lang.text(
        "upgrade.prompt",
        user_id,
        machine.level,
        LEVEL_SLOTS[machine.level],
        machine.level + 1,
        next_slots,
        cost,
    )
    if isinstance(bot, QQBot):
        prompt_data = (
            UniMessage()
            .style(
                await lang.text(
                    "upgrade.prompt_markdown",
                    user_id,
                    machine.level,
                    LEVEL_SLOTS[machine.level],
                    machine.level + 1,
                    next_slots,
                    cost,
                ),
                "markdown",
            )
            .keyboard(
                Button("enter", await lang.text("upgrade.button_yes", user_id), text="y"),
                Button("enter", await lang.text("upgrade.button_no", user_id), text="n"),
            )
        )
    try:
        agreed = await prompt(
            prompt_data,
            user_id,
            checker=lambda message: message.strip().lower() in ANSWER_ALIASES,
            retry=1,
            parser=lambda message: message.strip().lower() in AGREE_ANSWERS,
            ignore_error_details=False,
            allow_quit=False,
        )
    except (PromptTimeout, PromptRetryTooMuch):
        await lang.finish("upgrade.cancel", user_id)
    if not agreed:
        await lang.finish("upgrade.cancel", user_id)

    try:
        level, paid, slots = await try_upgrade(user_id)
    except NotEnoughVimcoin as error:
        await lang.finish("upgrade.no_vimcoin", user_id, error.need, error.have)
    if paid == 0:
        await lang.finish("upgrade.maxed", user_id)
    await lang.finish("upgrade.success", user_id, level, slots, paid)


@scheduler.scheduled_job("interval", minutes=1, id="craft_collect_finished")
async def auto_collect_finished() -> None:
    """定时把到点的合成产物发放到用户背包"""
    async with get_session() as session:
        user_ids = (
            await session.scalars(
                select(CraftingJob.user_id).where(CraftingJob.finish_time <= datetime.now()).distinct()
            )
        ).all()
    for user_id in user_ids:
        try:
            await collect_finished_jobs(str(user_id))
        except Exception as error:  # noqa: BLE001 - 定时任务需要吞下单个用户的异常
            logger.warning(f"[craft] 收集用户 {user_id} 的合成产物失败: {error!r}")
