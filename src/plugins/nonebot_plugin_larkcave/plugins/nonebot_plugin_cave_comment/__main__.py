from typing import Optional
from nonebot import on_message
from nonebot_plugin_alconna.uniseg import reply_fetch
from nonebot.adapters import Bot, Event
from nonebot.rule import to_me
from .message import get_cave_by_message_id
from nonebot.params import Depends
from ...lang import lang
from nonebot_plugin_orm import async_scoped_session
from .poster import post
from ....nonebot_plugin_larkutils import get_user_id, review_text

comment = on_message(rule=to_me())

async def get_belong_cave(bot: Bot, event: Event) -> Optional[int]:
    reply = await reply_fetch(event, bot)
    if reply is None:
        return
    return get_cave_by_message_id(reply.id)

async def get_message(event: Event) -> str:
    return event.get_plaintext()

@comment.handle()
async def _(
    session: async_scoped_session,
    content: str = Depends(get_message),
    user_id: str = get_user_id(),
    cave_id: Optional[int] = Depends(get_belong_cave)
) -> None:
    if cave_id is None or not content:
        await comment.finish()
    if not (result := await review_text(content))["compliance"]:
        await lang.finish("comment.review_fail", user_id, result["message"])
    await lang.finish("comment.success", user_id, await post(user_id, session, content, cave_id))