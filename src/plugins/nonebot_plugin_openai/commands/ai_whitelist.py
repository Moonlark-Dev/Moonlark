"""
/ai-whitelist 命令处理器
管理 AI 功能白名单，仅 superuser 可用
"""

from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..lang import lang
from ..models import AIWhitelist

ai_whitelist_cmd = on_alconna(
    Alconna(
        "ai-whitelist",
        Subcommand("list"),
        Subcommand("add", Args["group_id", str]),
        Subcommand("remove", Args["group_id", str]),
        Subcommand("enable", Args["group_id", str]),
        Subcommand("disable", Args["group_id", str]),
    ),
)


@ai_whitelist_cmd.assign("list")
async def handle_list(
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)
    async with get_session() as session:
        result = await session.scalars(select(AIWhitelist))
        entries = result.all()
    if not entries:
        await lang.finish("ai_whitelist.empty", user_id)
    lines = []
    for entry in entries:
        status = "✅" if entry.enabled else "❌"
        lines.append(f"{status} {entry.group_id}")
    await lang.finish("ai_whitelist.list", user_id, "\n".join(lines), len(entries))


@ai_whitelist_cmd.assign("add")
async def handle_add(
    group_id: str,
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)
    async with get_session() as session:
        existing = await session.scalar(select(AIWhitelist).where(AIWhitelist.group_id == group_id))
        if existing:
            await lang.finish("ai_whitelist.already_exists", user_id, group_id)
        session.add(AIWhitelist(group_id=group_id, enabled=True))
        await session.commit()
    await lang.finish("ai_whitelist.added", user_id, group_id)


@ai_whitelist_cmd.assign("remove")
async def handle_remove(
    group_id: str,
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)
    async with get_session() as session:
        entry = await session.scalar(select(AIWhitelist).where(AIWhitelist.group_id == group_id))
        if not entry:
            await lang.finish("ai_whitelist.not_found", user_id, group_id)
        await session.delete(entry)
        await session.commit()
    await lang.finish("ai_whitelist.removed", user_id, group_id)


@ai_whitelist_cmd.assign("enable")
async def handle_enable(
    group_id: str,
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)
    async with get_session() as session:
        entry = await session.scalar(select(AIWhitelist).where(AIWhitelist.group_id == group_id))
        if not entry:
            await lang.finish("ai_whitelist.not_found", user_id, group_id)
        entry.enabled = True
        await session.commit()
    await lang.finish("ai_whitelist.enabled", user_id, group_id)


@ai_whitelist_cmd.assign("disable")
async def handle_disable(
    group_id: str,
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)
    async with get_session() as session:
        entry = await session.scalar(select(AIWhitelist).where(AIWhitelist.group_id == group_id))
        if not entry:
            await lang.finish("ai_whitelist.not_found", user_id, group_id)
        entry.enabled = False
        await session.commit()
    await lang.finish("ai_whitelist.disabled", user_id, group_id)
