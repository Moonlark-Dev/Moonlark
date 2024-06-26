import base64
import math
import random
from datetime import date

import httpx
from nonebot import on_fullmatch
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Alconna, UniMessage, on_alconna
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from ..nonebot_plugin_render.render import render_template

from ..nonebot_plugin_email.utils.unread import get_unread_email_count

from ..nonebot_plugin_jrrp.jrrp import get_luck_value
from ..nonebot_plugin_larkuser.matcher import patch_matcher
from ..nonebot_plugin_larkuser.models import UserData
from ..nonebot_plugin_larkuser.utils.level import get_level_by_experience
from ..nonebot_plugin_larkuser.utils.user import get_user
from ..nonebot_plugin_larkutils import get_user_id
from .config import config
from .lang import lang
from .models import SignData

sign = on_alconna(Alconna("签到"), aliases={"签到", "sign"})
patch_matcher(sign)


def get_luck(user_id: str) -> str:
    value = get_luck_value(user_id)
    if 80 < value <= 100:
        return "a"
    elif 60 < value <= 80:
        return "b"
    elif 40 < value <= 60:
        return "c"
    elif 20 < value <= 40:
        return "d"
    elif 0 < value <= 20:
        return "e"
    else:
        return "f"


async def get_user_data(session: AsyncSession, user_id: str) -> SignData:
    try:
        return await session.get_one(SignData, {"user_id": user_id})
    except NoResultFound:
        session.add(SignData(user_id=user_id))
        await session.commit()
        return await get_user_data(session, user_id)


async def get_sign_exp(user_data: UserData, sign_data: SignData) -> int:
    level = get_level_by_experience(user_data.experience)
    exp = round(random.random() * level / 2 * max(user_data.favorability, 0.1) * min(sign_data.sign_days + 1, 15) + 1)
    if level <= 4:
        exp = round(exp * 1.3)
    user_data.experience += exp
    return exp


async def get_sign_vim(user_data: UserData, sign_data: SignData) -> float:
    level = get_level_by_experience(user_data.experience)
    vim = round(
        1
        + math.sqrt(
            math.sqrt(
                (1000 + random.random())
                * level
                * max(user_data.favorability, 0.1)
                / 5
                * min(sign_data.sign_days, 15)
                / 8
                + 1
            )
        )
        * 25
        * random.random(),
        1,
    )
    user_data.vimcoin += vim
    return vim


async def get_sign_fav(user_data: UserData) -> float:
    level = get_level_by_experience(user_data.experience)
    fav = round(0.001 * math.sqrt(level), 3)
    user_data.favorability += fav
    return fav


async def get_sign_days(sign_data: SignData) -> int:
    if (date.today() - sign_data.last_sign).days == 1:
        sign_data.sign_days += 1
    else:
        sign_data.sign_days = 1
    return sign_data.sign_days


async def get_hitokoto(user_id: str) -> str:
    # 是否有未读邮件
    if (count := await get_unread_email_count(user_id)) > 0:
        return await lang.text("image.email_unread", user_id, count)
    # 获取一言
    async with httpx.AsyncClient() as client:
        response = await client.get(config.hitokoto_api)
    if response.status_code == 200:
        return response.json()["hitokoto"]
    return await lang.text("image.hitokoto", user_id)


@sign.handle()
@patch_matcher(on_fullmatch(("sign", "签到"))).handle()
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    session = get_session()
    data = await get_user_data(session, user_id)
    user = await get_user(user_id, session)
    if (date.today() - data.last_sign).days < 1:
        await lang.finish("sign.signed", user_id)
    templates = {
        "nickname": user.nickname,
        "uid": await lang.text("image.uid", user_id, user_id),
        "hitokoto": await get_hitokoto(user_id),
        "signdays": {
            "text": await lang.text("image.signdays", user_id),
            "value": await lang.text("image.signdays_text", user_id, await get_sign_days(data)),
        },
        "exp": {
            "text": await lang.text("image.exp", user_id),
            "origin": user.experience,
            "add": await get_sign_exp(user, data),
            "now": user.experience,
        },
        "vim": {
            "text": await lang.text("image.vim", user_id),
            "origin": round(user.vimcoin, 1),
            "add": await get_sign_vim(user, data),
            "now": round(user.vimcoin, 1),
        },
        "fav": {
            "text": await lang.text("image.fav", user_id),
            "origin": round(user.favorability, 3),
            "add": await get_sign_fav(user),
            "now": round(user.favorability, 3),
        },
        "rank": {
            "text": await lang.text("image.rank", user_id),
            "value": await lang.text(
                "image.rank_text",
                user_id,
                len(
                    (await session.execute(select(SignData.user_id).where(SignData.last_sign == date.today())))
                    .scalars()
                    .all()
                )
                + 1,
            ),
        },
        "fortune": {
            "text": await lang.text("image.fortune", user_id),
            "value": await lang.text(f"luck.{get_luck(user_id)}", user_id),
        },
        "avatar": base64.b64encode(user.avatar).decode() if user.avatar is not None else None,
    }
    image = await render_template("sign.html.jinja", await lang.text("image.title", user_id), user_id, templates)
    msg = UniMessage().image(raw=image)
    data.last_sign = date.today()
    await session.commit()
    await session.close()
    await matcher.finish(await msg.export(), at_sender=True)
