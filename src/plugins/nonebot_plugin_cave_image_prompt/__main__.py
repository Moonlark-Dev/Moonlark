from nonebot import on_message
from nonebot.adapters import Event, Bot
from nonebot.rule import Rule
from nonebot_plugin_alconna import Image, UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.user import private_message as is_private_message
from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkcave.plugins.add.__main__ import post_cave
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session


def message_with_single_image(event: Event, bot: Bot) -> bool:
    """检查消息是否只包含一张图片"""
    message = UniMessage.generate_without_reply(event=event, bot=bot)
    return len(message) == 1 and isinstance(message[0], Image)


lang = LangHelper()
image_prompt = on_message(
    Rule(is_private_message) & Rule(message_with_single_image),
    priority=20,
    block=True,
)


async def ask_cave_submission(user_id: str) -> bool:
    """询问用户是否要投稿到 Cave"""
    yes_text = await lang.text("yes", user_id)
    no_text = await lang.text("no", user_id)
    return await prompt(
        await lang.text("ask", user_id),
        user_id,
        checker=lambda text: (text.strip() in [yes_text, no_text] or text.strip().lower() in ["y", "yes", "n", "no"]),
        parser=lambda text: (text.strip() == yes_text or text.strip().lower() in ["y", "yes"]),
        timeout=60,
        allow_quit=False,
    )


@image_prompt.handle()
async def handle_image_prompt(
    session: async_scoped_session, event: Event, bot: Bot, state: T_State, user_id: str = get_user_id()
) -> None:
    """处理单图片消息，询问是否投稿到 Cave"""
    image = UniMessage.generate_without_reply(event=event)[0]
    if not isinstance(image, Image):
        return
    # 询问用户是否要投稿
    if await ask_cave_submission(user_id):
        content = [image]
        await post_cave(content, user_id, event, bot, state, session)
    await lang.finish("cancelled", user_id)
