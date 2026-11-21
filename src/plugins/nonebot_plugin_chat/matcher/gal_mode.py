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
    disabled_stream = enabled
    if config is None:
        # 新记录同时承载私聊 Chat 开关，默认值为开启；开启备选回复时关闭流式发送
        config = PrivateChatConfig(user_id=user_id, enabled=True, gal_mode=enabled, stream=not enabled)
    else:
        disabled_stream = enabled and getattr(config, "stream", False)
        config.gal_mode = enabled
        if enabled:
            # 流式发送与私聊备选回复互斥：开启备选回复时关闭流式发送
            config.stream = False
    await session.merge(config)
    await session.commit()
    if disabled_stream:
        await lang.finish("command.gal_mode.enabled_stream_disabled", user_id)
    await lang.finish("command.gal_mode.enabled" if enabled else "command.gal_mode.disabled", user_id)
