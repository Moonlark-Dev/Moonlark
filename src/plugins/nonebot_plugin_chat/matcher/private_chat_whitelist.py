from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..lang import lang
from ..models import PrivateChatConfig

private_chat_whitelist_cmd = on_alconna(
    Alconna(
        ["private-chat-whitelist"],
        Args["action?", str]["user_id?", str],
    ),
)


@private_chat_whitelist_cmd.handle()
async def handle_private_chat_whitelist(
    action: str | None = None,
    target_user_id: str | None = None,
    is_superuser: bool = is_user_superuser(),
    user_id: str = get_user_id(),
) -> None:
    if not is_superuser:
        await lang.finish("private_chat_whitelist.no_permission", user_id)

    if action is None:
        await show_whitelist(user_id)
        return

    if action == "add" and target_user_id:
        await add_to_whitelist(user_id, target_user_id)
    elif action == "remove" and target_user_id:
        await remove_from_whitelist(user_id, target_user_id)
    elif action == "disable" and target_user_id:
        await set_whitelist_enabled(user_id, target_user_id, enabled=False)
    elif action == "enable" and target_user_id:
        await set_whitelist_enabled(user_id, target_user_id, enabled=True)
    else:
        await lang.finish("private_chat_whitelist.usage", user_id)


async def show_whitelist(user_id: str) -> None:
    async with get_session() as session:
        result = await session.scalars(select(PrivateChatConfig).where(PrivateChatConfig.enabled.is_(True)))
        entries = result.all()

    if not entries:
        await lang.finish("private_chat_whitelist.empty", user_id)

    lines = [f"✅ {entry.user_id}" for entry in entries]

    await lang.finish("private_chat_whitelist.list", user_id, "\n".join(lines), len(entries))


async def add_to_whitelist(user_id: str, target_user_id: str) -> None:
    async with get_session() as session:
        existing = await session.scalar(
            select(PrivateChatConfig).where(PrivateChatConfig.user_id == target_user_id),
        )
        if existing:
            if not existing.enabled:
                existing.enabled = True
                await session.commit()
                await lang.finish("private_chat_whitelist.enabled", user_id, target_user_id)
            await lang.finish("private_chat_whitelist.already_exists", user_id, target_user_id)

        session.add(PrivateChatConfig(user_id=target_user_id, enabled=True))
        await session.commit()

    await lang.finish("private_chat_whitelist.added", user_id, target_user_id)


async def remove_from_whitelist(user_id: str, target_user_id: str) -> None:
    async with get_session() as session:
        entry = await session.scalar(
            select(PrivateChatConfig).where(PrivateChatConfig.user_id == target_user_id),
        )
        if not entry:
            await lang.finish("private_chat_whitelist.not_found", user_id, target_user_id)

        await session.delete(entry)
        await session.commit()

    await lang.finish("private_chat_whitelist.removed", user_id, target_user_id)


async def set_whitelist_enabled(user_id: str, target_user_id: str, enabled: bool) -> None:
    async with get_session() as session:
        entry = await session.scalar(
            select(PrivateChatConfig).where(PrivateChatConfig.user_id == target_user_id),
        )
        if not entry:
            await lang.finish("private_chat_whitelist.not_found", user_id, target_user_id)

        entry.enabled = enabled
        await session.commit()

    key = "private_chat_whitelist.enabled" if enabled else "private_chat_whitelist.disabled"
    await lang.finish(key, user_id, target_user_id)
