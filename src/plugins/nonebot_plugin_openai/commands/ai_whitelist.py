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
        result = await session.execute(select(AIWhitelist.group_id).where(AIWhitelist.enabled.is_(True)))
        groups = [row[0] for row in result.all()]
    if groups:
        group_list = "\n".join(f" - {gid}" for gid in groups)
        await lang.finish("ai_whitelist.list", user_id, group_list)
    else:
        await lang.finish("ai_whitelist.list_empty", user_id)


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
            existing.enabled = True
        else:
            session.add(AIWhitelist(group_id=group_id, enabled=True))
        await session.commit()
    await lang.finish("ai_whitelist.add", user_id, group_id)


@ai_whitelist_cmd.assign("remove")
async def handle_remove(
    group_id: str,
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("ai_whitelist.no_permission", user_id)
    async with get_session() as session:
        existing = await session.scalar(select(AIWhitelist).where(AIWhitelist.group_id == group_id))
        if existing:
            await session.delete(existing)
            await session.commit()
            await lang.finish("ai_whitelist.remove", user_id, group_id)
        else:
            await lang.finish("ai_whitelist.remove_not_found", user_id, group_id)
