from nonebot import on_message
from nonebot.adapters import Event
from nonebot.adapters.qq import Bot
from nonebot.rule import Rule
from nonebot_plugin_alconna import Alconna, Args, Image, UniMessage, Text, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.user import private_message as is_private_message
from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkcave.utils.post import post_cave
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session, get_session

from .models import CaveImagePromptConfig

lang = LangHelper()


def message_with_single_image(event: Event, bot: Bot) -> bool:
    """检查消息是否只包含一张图片"""
    message = UniMessage.generate_without_reply(event=event, bot=bot)
    return len(message) == 1 and isinstance(message[0], Image)


async def is_prompt_enabled(user_id: str = get_user_id()) -> bool:
    """用户级开关：关闭时跳过投稿询问，让消息继续交给 chat 等后续插件处理"""
    async with get_session() as session:
        entry = await session.get(CaveImagePromptConfig, user_id)
    return entry is not None and entry.enabled


image_prompt = on_message(
    Rule(is_private_message) & Rule(message_with_single_image) & Rule(is_prompt_enabled),
    priority=20,
    block=True,
)

cave_prompt_cmd = on_alconna(
    Alconna("cave-prompt", Args["action?", str, ""]),
    use_cmd_start=True,
)


@cave_prompt_cmd.handle()
async def handle_cave_prompt(action: str, user_id: str = get_user_id()) -> None:
    """开关指令：/cave-prompt on|off，不带参数查看当前状态"""
    async with get_session() as session:
        entry = await session.get(CaveImagePromptConfig, user_id)
        if action == "on":
            if entry is None:
                session.add(CaveImagePromptConfig(user_id=user_id, enabled=True))
            else:
                entry.enabled = True
            await session.commit()
            await lang.finish("enabled", user_id)
        elif action == "off":
            if entry is None:
                session.add(CaveImagePromptConfig(user_id=user_id, enabled=False))
            else:
                entry.enabled = False
            await session.commit()
            await lang.finish("disabled", user_id)
        elif action == "":
            await lang.finish("status_on" if entry is not None and entry.enabled else "status_off", user_id)
        else:
            await lang.finish("usage", user_id)


async def ask_cave_submission(user_id: str) -> bool:
    """询问用户是否要投稿到 Cave"""
    yes_text = await lang.text("yes", user_id)
    no_text = await lang.text("no", user_id)
    return await prompt(
        await lang.text("ask", user_id),
        user_id,
        checker=lambda text: text.strip() in [yes_text, no_text] or text.strip().lower() in ["y", "yes", "n", "no"],
        parser=lambda text: text.strip() == yes_text or text.strip().lower() in ["y", "yes"],
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
        content: list[Image | Text] = [image]
        await post_cave(content, user_id, event, bot, state, session)
    await lang.finish("cancelled", user_id)
