#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.adapters.qq import Bot
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot_plugin_alconna import Alconna, Args, Image, Text, UniMessage, on_alconna
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.user import private_message as is_private_message
from nonebot_plugin_larkuser import prompt
from nonebot_plugin_orm import async_scoped_session, get_session

from ..lang import lang
from ..models import CaveImagePromptConfig
from ..utils.post import post_cave


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
            await lang.finish("prompt.enabled", user_id)
        elif action == "off":
            if entry is None:
                session.add(CaveImagePromptConfig(user_id=user_id, enabled=False))
            else:
                entry.enabled = False
            await session.commit()
            await lang.finish("prompt.disabled", user_id)
        elif action == "":
            await lang.finish(
                "prompt.status_on" if entry is not None and entry.enabled else "prompt.status_off",
                user_id,
            )
        else:
            await lang.finish("prompt.usage", user_id)


async def ask_cave_submission(user_id: str) -> bool:
    """询问用户是否要投稿到 Cave"""
    yes_text = await lang.text("prompt.yes", user_id)
    no_text = await lang.text("prompt.no", user_id)
    return await prompt(
        await lang.text("prompt.ask", user_id),
        user_id,
        checker=lambda text: text.strip() in [yes_text, no_text] or text.strip().lower() in ["y", "yes", "n", "no"],
        parser=lambda text: text.strip() == yes_text or text.strip().lower() in ["y", "yes"],
        timeout=60,
        allow_quit=False,
    )


@image_prompt.handle()
async def handle_image_prompt(
    session: async_scoped_session,
    event: Event,
    bot: Bot,
    state: T_State,
    user_id: str = get_user_id(),
) -> None:
    """处理单图片消息，询问是否投稿到 Cave"""
    image = UniMessage.generate_without_reply(event=event)[0]
    if not isinstance(image, Image):
        return
    # 询问用户是否要投稿
    if await ask_cave_submission(user_id):
        content: list[Image | Text] = [image]
        await post_cave(content, user_id, event, bot, state, session)
    await lang.finish("prompt.cancelled", user_id)
