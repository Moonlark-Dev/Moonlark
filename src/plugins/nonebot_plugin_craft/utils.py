"""合成机的读写逻辑：机器等级、合成任务的生命周期管理。"""

from dataclasses import dataclass
from datetime import datetime

from nonebot_plugin_bag.models import Bag
from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import func, select

from .models import CraftingJob, CraftingMachine
from .recipes import LEVEL_SLOTS, MAX_LEVEL, UPGRADE_COSTS, Recipe, RECIPES


@dataclass
class MachineInfo:
    """合成机快照（不持有 ORM 对象）"""

    user_id: str
    level: int


@dataclass
class JobInfo:
    """合成任务快照（不持有 ORM 对象）"""

    id_: int
    user_id: str
    recipe_id: str
    time: datetime
    finish_time: datetime


def _job_snapshot(job: CraftingJob) -> JobInfo:
    return JobInfo(
        id_=job.id_,
        user_id=job.user_id,
        recipe_id=job.recipe_id,
        time=job.time,
        finish_time=job.finish_time,
    )


class NoFreeSlot(Exception):
    """合成槽位已满"""

    def __init__(self, free: int) -> None:
        self.free = free


class NotEnoughMaterial(Exception):
    """材料不足"""

    def __init__(self, item_id: str, need: int, have: int) -> None:
        self.item_id = item_id
        self.need = need
        self.have = have


class NotEnoughVimcoin(Exception):
    def __init__(self, need: float, have: float) -> None:
        self.need = need
        self.have = have


async def get_machine(user_id: str) -> MachineInfo:
    """获取用户的合成机快照，首次使用时自动创建（等级 1，2 个槽位）"""
    async with get_session() as session:
        machine = await session.get(CraftingMachine, user_id)
        if machine is None:
            machine = CraftingMachine(user_id=user_id, level=1)
            session.add(machine)
            await session.flush()
        level = machine.level
        await session.commit()
    return MachineInfo(user_id=user_id, level=level)


async def get_slots_info(user_id: str) -> tuple[int, int]:
    """获取合成机槽位信息：(总数, 已占用数)"""
    machine = await get_machine(user_id)
    total = LEVEL_SLOTS.get(machine.level, 2)
    async with get_session() as session:
        used = int(
            (await session.scalar(select(func.count()).select_from(CraftingJob).where(CraftingJob.user_id == user_id)))
            or 0
        )
        return total, used


async def try_upgrade(user_id: str) -> tuple[int, int, int]:
    """升级合成机。

    Returns:
        (新等级, 本次升级费用, 升级后的槽位数)。已满级时返回 (当前等级, 0, 当前槽位数)。

    Raises:
        NotEnoughVimcoin: VimCoin 不足
    """
    machine = await get_machine(user_id)
    slots = LEVEL_SLOTS[machine.level]
    if machine.level >= MAX_LEVEL:
        return machine.level, 0, slots
    cost = UPGRADE_COSTS[machine.level + 1]

    from nonebot_plugin_larkuser import get_user

    user = await get_user(user_id)
    if not await user.has_vimcoin(cost):
        raise NotEnoughVimcoin(cost, round(user.get_vimcoin(), 1))
    if not await user.use_vimcoin(cost):
        raise NotEnoughVimcoin(cost, round(user.get_vimcoin(), 1))

    async with get_session() as session:
        db_machine = await session.get(CraftingMachine, user_id)
        if db_machine is None:
            db_machine = CraftingMachine(user_id=user_id, level=1)
            session.add(db_machine)
            await session.flush()
        db_machine.level += 1
        level = db_machine.level
        await session.commit()
    return level, cost, LEVEL_SLOTS[level]


async def _get_material_count(session: AsyncSession, user_id: str, item_id: str) -> int:
    return int(
        (
            await session.scalar(
                select(func.coalesce(func.sum(Bag.count), 0)).where(Bag.user_id == user_id, Bag.item_id == item_id)
            )
        )
        or 0
    )


async def _deduct_materials(session: AsyncSession, user_id: str, inputs: dict[str, int]) -> None:
    """在给定会话中扣除配方材料，不足时抛出 NotEnoughMaterial（不执行扣除）"""
    for item_id, need in inputs.items():
        have = await _get_material_count(session, user_id, item_id)
        if have < need:
            raise NotEnoughMaterial(item_id, need, have)


async def start_job(user_id: str, recipe: Recipe) -> JobInfo:
    """开始一个合成任务（占用一个槽位、扣除材料与 VimCoin）。

    Raises:
        NoFreeSlot: 槽位已满
        NotEnoughMaterial: 材料不足
        NotEnoughVimcoin: VimCoin 不足
    """
    total, used = await get_slots_info(user_id)
    if used >= total:
        raise NoFreeSlot(total - used)

    from nonebot_plugin_larkuser import get_user

    user = await get_user(user_id)
    if not await user.has_vimcoin(recipe.vimcoin):
        raise NotEnoughVimcoin(recipe.vimcoin, round(user.get_vimcoin(), 1))
    if not await user.use_vimcoin(recipe.vimcoin):
        raise NotEnoughVimcoin(recipe.vimcoin, round(user.get_vimcoin(), 1))

    async with get_session() as session:
        try:
            await _deduct_materials(session, user_id, recipe.inputs)
        except NotEnoughMaterial as error:
            await session.rollback()
            await user.add_vimcoin(recipe.vimcoin)  # 材料不足，退还 VimCoin
            raise error
        for item_id, need in recipe.inputs.items():
            remaining = need
            bag_rows = (
                await session.scalars(
                    select(Bag).where(Bag.user_id == user_id, Bag.item_id == item_id).order_by(Bag.bag_index)
                )
            ).all()
            for row in bag_rows:
                if remaining <= 0:
                    break
                amount = min(remaining, row.count)
                row.count -= amount
                remaining -= amount
                if row.count <= 0:
                    await session.delete(row)
        now = datetime.now()
        job = CraftingJob(user_id=user_id, recipe_id=recipe.id, time=now, finish_time=now + recipe.duration)
        session.add(job)
        await session.flush()
        snapshot = _job_snapshot(job)
        await session.commit()
        return snapshot


async def collect_finished_jobs(user_id: str) -> list[tuple[Recipe, int]]:
    """收集已完成（超过合成时间）的任务，产物发放到背包，返回 (配方, 产物数量) 列表"""
    async with get_session() as session:
        jobs = (
            await session.scalars(
                select(CraftingJob)
                .where(CraftingJob.user_id == user_id, CraftingJob.finish_time <= datetime.now())
                .order_by(CraftingJob.finish_time)
            )
        ).all()
        # 必须在删除前取出快照：commit 后 ORM 实例过期
        finished = [_job_snapshot(job) for job in jobs]
        for job in jobs:
            await session.delete(job)
        await session.commit()

    counts: dict[str, int] = {}
    for job in finished:
        if job.recipe_id not in RECIPES:
            continue
        counts[job.recipe_id] = counts.get(job.recipe_id, 0) + 1
    if not counts:
        return []

    deliveries: list[tuple[Recipe, int]] = []
    from nonebot_plugin_items.utils.get import get_item
    from nonebot_plugin_items.utils.string import get_location_by_id

    for recipe_id, job_count in counts.items():
        recipe = RECIPES[recipe_id]
        output_count = recipe.output_count * job_count
        stack = await get_item(get_location_by_id(recipe.output_id), user_id, output_count)
        await give_item(user_id, stack)
        deliveries.append((recipe, output_count))
    return deliveries


async def get_running_jobs(user_id: str) -> list[JobInfo]:
    """获取尚未完成的合成任务（用于展示进度）"""
    async with get_session() as session:
        jobs = (
            await session.scalars(
                select(CraftingJob)
                .where(CraftingJob.user_id == user_id, CraftingJob.finish_time > datetime.now())
                .order_by(CraftingJob.finish_time)
            )
        ).all()
        return [_job_snapshot(job) for job in jobs]


def get_upgrade_cost(level: int) -> int | None:
    """获取从给定等级升级到下一级需要的 VimCoin，满级返回 None"""
    return UPGRADE_COSTS.get(level + 1)


def format_remaining(finish_time: datetime, now: datetime | None = None) -> str:
    """把任务的剩余时间格式化成可读文本（如 5 小时 3 分钟）"""
    remaining = max((finish_time - (now or datetime.now())).total_seconds(), 0.0)
    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{minutes} 分钟"


async def get_item_name(item_id: str, user_id: str) -> str:
    """获取物品的显示名称"""
    from nonebot_plugin_items.utils.get import get_item
    from nonebot_plugin_items.utils.string import get_location_by_id

    stack = await get_item(get_location_by_id(item_id), user_id)
    return await stack.getName()
