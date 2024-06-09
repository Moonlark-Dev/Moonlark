from typing import Literal
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from ..utils.claim import claim_email
from ..lang import lang
from ..models import EmailUser
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import email


@email.assign("claim.email_id")
async def _(
    session: async_scoped_session,
    email_id: int | Literal["all"],
    user_id: str = get_user_id()
) -> None:
    result = await session.scalars(select(EmailUser).where(
        EmailUser.user_id == user_id, EmailUser.is_claimed.is_not(True)))
    claimed_items = []
    email_count = 0
    for email_data in result:
        if email_data.email_id == email_id or email_id == "all":
            claimed_items.extend(await claim_email(email_data.email_id, user_id))
            email_data.is_claimed = True
            email_count += 1
    await session.commit()
    index = 0
    await email.finish(UniMessage().text(
        await lang.text("claim.done", user_id, email_count, len(claimed_items))).image(
        raw=await md_to_pic("\n".join([
            await lang.text("claim.markdown", user_id, index := index + 1, await item.getName, item.count)
            for item in claimed_items
        ]) or await lang.text("claim.no_item", user_id)
    )))
    
