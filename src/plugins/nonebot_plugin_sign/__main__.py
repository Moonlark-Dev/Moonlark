import base64
import math
import random
from datetime import date

import httpx

from typing import TypedDict
from nonebot import on_fullmatch
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Alconna, UniMessage, on_alconna
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from nonebot_plugin_render.render import render_template
from nonebot_plugin_email.utils.unread import get_unread_email_count
from nonebot_plugin_jrrp.jrrp import get_luck_value
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.utils.waiter import prompt, PromptTimeout, PromptRetryTooMuch
from nonebot_plugin_larkuser.user.base import MoonlarkUser
from nonebot_plugin_larkutils import get_user_id
from .config import config
from .lang import lang
from .models import SignData

sign = on_alconna(Alconna("签到"), aliases={"签到", "sign"})
patch_matcher(sign)


class SignClaimData(TypedDict):
    text: str
    origin: float | int
    add: float | int
    now: float | int


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


async def get_sign_data(session: AsyncSession, user_id: str) -> SignData:
    try:
        return await session.get_one(SignData, {"user_id": user_id})
    except NoResultFound:
        session.add(SignData(user_id=user_id))
        await session.commit()
        return await get_sign_data(session, user_id)


async def get_sign_exp(user: MoonlarkUser, sign_data: SignData) -> SignClaimData:
    level = user.get_level()
    origin_exp = user.get_experience()
    exp = round(random.random() * level / 2 * max(user.get_fav(), 0.1) * min(sign_data.sign_days + 1, 15) + 1)
    if level <= 4:
        exp = round(exp * 1.3)
    await user.add_experience(exp)
    return {
        "text": await lang.text("image.exp", user.user_id),
        "now": user.get_experience(),
        "add": exp,
        "origin": origin_exp,
    }


async def get_sign_vim(user_data: MoonlarkUser, sign_data: SignData) -> SignClaimData:
    level = user_data.get_level()
    origin = user_data.get_vimcoin()
    vim = round(
        1
        + math.sqrt(
            math.sqrt(
                (1000 + random.random()) * level * max(user_data.get_fav(), 0.1) / 5 * min(sign_data.sign_days, 15) / 8
                + 1
            )
        )
        * 25
        * random.random(),
        1,
    )
    await user_data.add_vimcoin(vim)
    return {
        "text": await lang.text("image.vim", user_data.user_id),
        "add": vim,
        "origin": origin,
        "now": user_data.get_vimcoin(),
    }


async def get_sign_fav(user_data: MoonlarkUser) -> SignClaimData:
    origin = user_data.get_fav()
    fav = 0.001
    await user_data.add_fav(fav)
    return {
        "text": await lang.text("image.fav", user_data.user_id),
        "add": fav,
        "now": user_data.get_fav(),
        "origin": origin,
    }


async def resign(sign_data: SignData, user: MoonlarkUser) -> bool:
    if (days := (date.today() - sign_data.last_sign).days - 1) >= 15:
        return False
    needed_vimcoin = days * 30
    if not await user.has_vimcoin(needed_vimcoin):
        return False
    try:
        await prompt(
            await lang.text("resign.prompt", sign_data.user_id, days, needed_vimcoin),
            sign_data.user_id,
            retry=1,
            parser=lambda message: message.lower().startswith("y"),
            ignore_error_details=False,
            allow_quit=False,
        )
    except (PromptTimeout, PromptRetryTooMuch):
        return False
    got_vimcoin = 0
    got_experience = 0
    for _ in range(days):
        sign_data.sign_days += 1
        got_vimcoin += (await get_sign_vim(user, sign_data))["add"]
        got_experience += (await get_sign_exp(user, sign_data))["add"]
    await lang.send("resign.success", user.user_id, days, got_vimcoin, got_experience)
    await user.add_fav(0.001)
    sign_data.sign_days += 1
    return True


async def get_sign_days(sign_data: SignData, user: MoonlarkUser) -> int:
    if (date.today() - sign_data.last_sign).days == 1:
        sign_data.sign_days += 1
    elif not await resign(sign_data, user):
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
    data = await get_sign_data(session, user_id)
    user = await get_user(user_id)
    if (date.today() - data.last_sign).days < 1:
        await lang.finish("sign.signed", user_id)
    templates = {
        "signdays": {
            "text": await lang.text("image.signdays", user_id),
            "value": await lang.text("image.signdays_text", user_id, await get_sign_days(data, user)),
        },
        "nickname": user.nickname,
        "uid": await lang.text("image.uid", user_id, user_id),
        "hitokoto": await get_hitokoto(user_id),
        "exp": await get_sign_exp(user, data),
        "vim": await get_sign_vim(user, data),
        "fav": await get_sign_fav(user),
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
    data.last_sign = date.today()
    await session.commit()
    await session.close()
    image = await render_template("sign.html.jinja", await lang.text("image.title", user_id), user_id, templates)
    msg = UniMessage().image(raw=image)
    await matcher.finish(await msg.export(), at_sender=True)
