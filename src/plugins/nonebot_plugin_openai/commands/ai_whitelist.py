"""
/ai_whitelist 命令处理器
管理 AI 功能白名单，仅 superuser 可用
"""

from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..lang import lang
from ..models import AIWhitelist

ai_whitelist_cmd = on_alconna(
    Alconna(
        "ai_whitelist",
        Args["action?", str]["group_id?", str],
    )
)


@ai_whitelist_cmd.handle()
async def handle_ai_whitelist(
    action: str | None = None,
    group_id: str | None = None,
    is_superuser: bool = is_user_superuser(),
    user_id: str = get_user_id(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)

    if action is None:
        await show_whitelist(user_id)
        return

    if action == "add" and group_id:
        await add_to_whitelist(user_id, group_id)
    elif action == "remove" and group_id:
        await remove_from_whitelist(user_id, group_id)
    elif action == "disable" and group_id:
        await set_whitelist_enabled(user_id, group_id, False)
    elif action == "enable" and group_id:
        await set_whitelist_enabled(user_id, group_id, True)
    else:
        await lang.finish("ai_whitelist.usage", user_id)


async def show_whitelist(user_id: str) -> None:
    """显示白名单列表"""
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


async def add_to_whitelist(user_id: str, group_id: str) -> None:
    """添加群聊到白名单"""
    async with get_session() as session:
        existing = await session.scalar(
            select(AIWhitelist).where(AIWhitelist.group_id == group_id)
        )
        if existing:
            await lang.finish("ai_whitelist.already_exists", user_id, group_id)

        session.add(AIWhitelist(group_id=group_id, enabled=True))
        await session.commit()

    await lang.finish("ai_whitelist.added", user_id, group_id)


async def remove_from_whitelist(user_id: str, group_id: str) -> None:
    """从白名单移除群聊"""
    async with get_session() as session:
        entry = await session.scalar(
            select(AIWhitelist).where(AIWhitelist.group_id == group_id)
        )
        if not entry:
            await lang.finish("ai_whitelist.not_found", user_id, group_id)

        await session.delete(entry)
        await session.commit()

    await lang.finish("ai_whitelist.removed", user_id, group_id)


async def set_whitelist_enabled(user_id: str, group_id: str, enabled: bool) -> None:
    """启用/禁用白名单中的群聊"""
    async with get_session() as session:
        entry = await session.scalar(
            select(AIWhitelist).where(AIWhitelist.group_id == group_id)
        )
        if not entry:
            await lang.finish("ai_whitelist.not_found", user_id, group_id)

        entry.enabled = enabled
        await session.commit()

    key = "ai_whitelist.enabled" if enabled else "ai_whitelist.disabled"
    await lang.finish(key, user_id, group_id)
