from nonebot import on_command
from nonebot.adapters import Event, Message
from nonebot.params import CommandArg
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.user import private_message
from nonebot_plugin_orm import async_scoped_session

from ..lang import lang
from ..models import PrivateChatConfig

gal_mode = on_command("gal-mode")


@gal_mode.handle()
async def _(
    event: Event,
    session: async_scoped_session,
    message: Message = CommandArg(),
    user_id: str = get_user_id(),
) -> None:
    if not await private_message(event):
        await lang.finish("command.gal_mode.private_only", user_id)

    config = await session.get(PrivateChatConfig, {"user_id": user_id})
    action = message.extract_plain_text().strip().lower()
    if action not in ("on", "off"):
        key = (
            "command.gal_mode.current_on" if config is not None and config.gal_mode else "command.gal_mode.current_off"
        )
        await lang.finish(key, user_id)

    enabled = action == "on"
    if config is None:
        # 新记录同时承载私聊 Chat 开关，默认值为开启
        config = PrivateChatConfig(user_id=user_id, enabled=True, gal_mode=enabled)
    else:
        config.gal_mode = enabled
    await session.merge(config)
    await session.commit()
    await lang.finish("command.gal_mode.enabled" if enabled else "command.gal_mode.disabled", user_id)
