from datetime import datetime

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Button, Subcommand, UniMessage, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkuser.utils.waiter import PromptRetryTooMuch, PromptTimeout, prompt
from nonebot_plugin_larkutils import escape_markdown, get_user_id
from nonebot_plugin_orm import get_session

from sqlalchemy import select

from .lang import lang
from .models import CraftingJob
from .panel import (
    PanelData,
    PanelJob,
    build_panel_buttons,
    build_panel_markdown,
    build_panel_text,
    build_start_buttons,
)
from .recipes import LEVEL_SLOTS, RECIPES
from .utils import (
    NoFreeSlot,
    NotEnoughMaterial,
    NotEnoughVimcoin,
    collect_finished_jobs,
    format_item_list,
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


async def _maybe_collect(user_id: str) -> tuple[str, str]:
    """收集已完成的任务，返回 (收集文本, 产物文本)"""
    deliveries = await collect_finished_jobs(user_id)
    if not deliveries:
        return "", ""
    delivered = await format_item_list([(recipe.output_id, count) for recipe, count in deliveries], user_id)
    return await lang.text("list.collected", user_id, delivered), delivered


async def _build_panel_data(user_id: str) -> PanelData:
    """查询合成机状态、槽位与进行中的任务，组装成面板数据"""
    machine = await get_machine(user_id)
    total, used = await get_slots_info(user_id)
    collected_text, delivered = await _maybe_collect(user_id)
    jobs = []
    for job in await get_running_jobs(user_id):
        recipe = RECIPES.get(job.recipe_id)
        name = await get_item_name(recipe.output_id, user_id) if recipe else job.recipe_id
        jobs.append(
            PanelJob(
                name=name,
                count=recipe.output_count if recipe else 1,
                remaining=format_remaining(job.finish_time),
            )
        )
    return PanelData(
        level=machine.level,
        total=total,
        used=used,
        collected=collected_text,
        jobs=jobs,
    )


async def send_panel(bot: Bot, event: Event, user_id: str, data: PanelData) -> None:
    """发送合成机面板：QQ 官方用 markdown + 按钮，其它适配器渲染成图片（失败回退纯文本）"""
    if isinstance(bot, QQBot):
        message = (
            UniMessage()
            .style(await build_panel_markdown(user_id, data, clickable=True), "markdown")
            .keyboard(*await build_panel_buttons(user_id))
        )
        await message.send(target=event, bot=bot)
        await craft.finish()

    try:
        image = await md_to_pic(await build_panel_markdown(user_id, data, clickable=False))
    except Exception:
        logger.exception("渲染合成机面板失败，回退到文本消息")
        await craft.finish(await build_panel_text(user_id, data))
        return
    await craft.finish(UniMessage().image(raw=image))


@craft.assign("$main")
async def _(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    await send_panel(bot, event, user_id, await _build_panel_data(user_id))


async def send_started(bot: Bot, event: Event, user_id: str, name: str, started: int, remaining: str) -> None:
    """发送开始合成提示：QQ 官方附上「查看合成机」按钮，其它适配器保持纯文本"""
    if isinstance(bot, QQBot):
        message = (
            UniMessage()
            .style(await lang.text("start.started", user_id, escape_markdown(name), started, remaining), "markdown")
            .keyboard(*await build_start_buttons(user_id))
        )
        await message.send(target=event, bot=bot)
        await craft.finish()
    await lang.finish("start.started", user_id, name, started, remaining)


@craft.assign("start")
async def _(bot: Bot, event: Event, recipe_id: str, count: int = 1, user_id: str = get_user_id()) -> None:
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
    await send_started(bot, event, user_id, name, started, format_remaining(finish_time))


@craft.assign("collect")
async def _(user_id: str = get_user_id()) -> None:
    deliveries = await collect_finished_jobs(user_id)
    if not deliveries:
        await lang.finish("collect.done", user_id)
    delivered = await format_item_list([(recipe.output_id, count) for recipe, count in deliveries], user_id)
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
