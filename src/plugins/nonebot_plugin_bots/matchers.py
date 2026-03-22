from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkutils import get_user_id, is_private_message
from nonebot_plugin_alconna import UniMessage

from .models import UserBotPrivateChatSettings


async def handle_pm_command(bot: Bot, event: Event, action: str) -> None:
    """处理 .pm on/off 命令"""
    user_id = await get_user_id()(bot, event)
    bot_id = bot.self_id

    async with get_session() as session:
        # 获取或创建设置记录
        settings = await session.get(UserBotPrivateChatSettings, {"user_id": user_id, "bot_id": bot_id})

        if settings is None:
            # 如果记录不存在，创建新记录
            settings = UserBotPrivateChatSettings(user_id=user_id, bot_id=bot_id, private_chat_enabled=(action == "on"))
            session.add(settings)
        else:
            # 更新现有记录
            settings.private_chat_enabled = action == "on"

        await session.commit()

        # 发送响应消息
        if action == "on":
            await UniMessage.text("私聊已开启").send()
        else:
            await UniMessage.text("私聊已关闭").send()


# 创建 .pm on 命令处理器
pm_on = on_command(".pm", priority=10, block=True)


@pm_on.handle()
async def _(bot: Bot, event: Event) -> None:
    """处理 .pm on/off 命令"""
    # 只在私聊中响应
    if not await is_private_message()(bot, event):
        await pm_on.finish()

    # 获取消息内容
    message = event.get_plaintext().strip()

    # 检查是否为 .pm on 或 .pm off
    if message == ".pm on":
        await handle_pm_command(bot, event, "on")
    elif message == ".pm off":
        await handle_pm_command(bot, event, "off")
    else:
        await pm_on.finish()
