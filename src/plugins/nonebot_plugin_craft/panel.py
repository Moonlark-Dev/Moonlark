"""合成机面板的构建与发送。

QQ 官方机器人使用原生 markdown 消息 + 键盘按钮：标题、状态与分组用小标题和引用块
拉开层次，每条配方下方用 ``<qqbot-cmd-input>`` 提供「开始合成」入口。

其它适配器没有 markdown 消息，改为把同一份 markdown 用 ``md_to_pic`` 渲染成图片，
层次与 QQ 侧保持一致；渲染失败时回退到纯文本面板。
"""

from __future__ import annotations

from dataclasses import dataclass

from nonebot_plugin_alconna import Button
from nonebot_plugin_larkutils import escape_cmd_input, escape_markdown
from nonebot_plugin_larkutils.command import get_command_prefix

from .lang import lang
from .recipes import LEVEL_SLOTS, MAX_LEVEL, RECIPES, Recipe
from .utils import format_item_list, get_item_name, get_upgrade_cost


@dataclass(frozen=True)
class PanelJob:
    """面板里展示的一条进行中的合成"""

    name: str
    count: int
    remaining: str


@dataclass(frozen=True)
class PanelData:
    """构建面板需要的全部数据（在 handler 里一次性查好）"""

    level: int
    total: int
    used: int
    collected: str
    jobs: list[PanelJob]


def format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{minutes} 分钟"


async def _format_upgrade(user_id: str, level: int) -> str:
    """升级状态：升级花费与下一级槽位，满级时给出提示"""
    cost = get_upgrade_cost(level)
    if cost is None:
        return await lang.text("panel.upgrade_max", user_id, MAX_LEVEL)
    return await lang.text("panel.upgrade", user_id, level + 1, LEVEL_SLOTS[level + 1], cost)


async def build_panel_markdown(user_id: str, data: PanelData, clickable: bool) -> str:
    """构建合成机面板 markdown。

    Args:
        clickable: QQ 官方机器人传 True，配方下生成 ``<qqbot-cmd-input>`` 快捷入口；
            其它适配器传 False，改为展示完整指令，避免未知标签被渲染成空白。
    """
    prefix = get_command_prefix()
    blocks = [
        await lang.text("panel.title", user_id, data.level),
        await lang.text("panel.status", user_id, data.used, data.total, await _format_upgrade(user_id, data.level)),
    ]
    if data.collected:
        blocks.append(await lang.text("panel.collected", user_id, data.collected))

    job_blocks = [await lang.text("panel.jobs_title", user_id)]
    if data.jobs:
        for job in data.jobs:
            job_blocks.append(
                await lang.text("panel.job", user_id, escape_markdown(job.name), job.count, job.remaining)
            )
    else:
        job_blocks.append(await lang.text("panel.jobs_empty", user_id, data.total - data.used))
    blocks.append("\n".join(job_blocks))

    recipe_blocks = [await lang.text("panel.recipes_title", user_id)]
    for recipe in RECIPES.values():
        output_name = await get_item_name(recipe.output_id, user_id)
        inputs = escape_markdown(await format_item_list(recipe.inputs.items(), user_id))
        lines = [
            await lang.text(
                "panel.recipe_title",
                user_id,
                escape_markdown(output_name),
                recipe.output_count,
                format_duration(recipe.duration.total_seconds()),
            ),
            await lang.text("panel.recipe_meta", user_id, inputs, recipe.vimcoin),
        ]
        command = f"{prefix}craft start {recipe.id} 1"
        if clickable:
            lines.append(
                await lang.text(
                    "panel.recipe_start",
                    user_id,
                    escape_cmd_input(command),
                    escape_cmd_input(f"开始合成{output_name}"),
                )
            )
        else:
            lines.append(await lang.text("panel.recipe_start_plain", user_id, command))
        recipe_blocks.append("\n".join(lines))
    blocks.append("\n\n".join(recipe_blocks))

    blocks.append(await lang.text("panel.footer" if clickable else "panel.footer_plain", user_id))
    return "\n\n".join(blocks)


async def build_panel_text(user_id: str, data: PanelData) -> str:
    """构建纯文本面板，供非 QQ 适配器渲染成图片失败时回退"""
    lines = [
        await lang.text("list.title", user_id, data.level, data.total),
        await lang.text("list.slots", user_id, data.used, data.total),
    ]
    cost = get_upgrade_cost(data.level)
    if cost is not None:
        lines.append(await lang.text("list.upgrade", user_id, cost, data.level + 1, LEVEL_SLOTS[data.level + 1]))
    else:
        lines.append(await lang.text("list.upgrade_max", user_id, MAX_LEVEL))
    if data.collected:
        lines.append(data.collected)
    if data.jobs:
        lines.append(await lang.text("list.jobs_title", user_id))
        for job in data.jobs:
            lines.append(await lang.text("list.job", user_id, job.name, job.remaining))
    else:
        lines.append(await lang.text("list.jobs_empty", user_id, data.total - data.used, data.total))
    if RECIPES:
        lines.append(await lang.text("recipe.title", user_id))
        for recipe in RECIPES.values():
            lines.append(await _build_recipe_text(user_id, recipe))
    lines.append(await lang.text("list.footer", user_id))
    return "\n".join(lines)


async def _build_recipe_text(user_id: str, recipe: Recipe) -> str:
    name = await get_item_name(recipe.output_id, user_id)
    inputs = await format_item_list(recipe.inputs.items(), user_id)
    return await lang.text(
        "recipe.item",
        user_id,
        recipe.id,
        name,
        recipe.output_count,
        inputs,
        recipe.vimcoin,
        format_duration(recipe.duration.total_seconds()),
    )


async def build_panel_buttons(user_id: str) -> list[Button]:
    """QQ 官方机器人面板下方的操作按钮：收取成品、升级合成机、刷新面板"""
    prefix = get_command_prefix()
    return [
        Button("enter", await lang.text("panel.button_collect", user_id), text=f"{prefix}craft collect"),
        Button("enter", await lang.text("panel.button_upgrade", user_id), text=f"{prefix}craft upgrade"),
        Button("enter", await lang.text("panel.button_refresh", user_id), text=f"{prefix}craft"),
    ]


async def build_start_buttons(user_id: str) -> list[Button]:
    """开始合成提示下方的操作按钮：回到合成机面板"""
    return [Button("enter", await lang.text("start.button_view_machine", user_id), text=f"{get_command_prefix()}craft")]
