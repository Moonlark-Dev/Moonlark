import asyncio
import base64
import math
import random
from datetime import date
from typing import Optional

import httpx
from nonebot import logger
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Alconna, UniMessage, on_alconna
from nonebot_plugin_bag.config import config as bag_config
from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_bag.utils.item import get_bag_items
from nonebot_plugin_chat.utils.gift_drop import get_gift_drop_manager
from nonebot_plugin_email.utils.unread import get_unread_email_count
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_larksetu import get_landscape_image
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkuser.utils.waiter import PromptRetryTooMuch, PromptTimeout, prompt
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_orm import AsyncSession, get_session
from nonebot_plugin_render.render import render_template
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from .config import config
from .lang import lang
from .models import SignData

sign = on_alconna(Alconna("签到"), aliases={"签到", "sign"})
patch_matcher(sign)

# 全局锁，保护 SignData 数据操作
_global_sign_lock = asyncio.Lock()


async def _get_luck(user_id: str) -> str:
    value = await get_luck_value(user_id)
    if 80 < value:
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


async def _get_sign_data(session: AsyncSession, user_id: str) -> SignData:
    try:
        return await session.get_one(SignData, {"user_id": user_id})
    except NoResultFound:
        session.add(SignData(user_id=user_id))
        await session.commit()
        return await _get_sign_data(session, user_id)


async def _try_sign_gift_drop(user_id: str) -> Optional[tuple[str, str]]:
    gift_id = get_gift_drop_manager().select_gift()
    namespace, path = gift_id.split(":", 1)
    location = ResourceLocation(namespace, path)

    bag_items = await get_bag_items(user_id)
    for bag_item in bag_items:
        if str(bag_item.stack.item.getLocation()) == gift_id:
            if not bag_item.stack.isAddable():
                logger.info(f"Sign gift drop skipped (stack full): user={user_id}, gift={gift_id}")
                return None
            break
    else:
        if len(bag_items) >= bag_config.bag_max_size:
            logger.info(f"Sign gift drop skipped (bag full): user={user_id}, gift={gift_id}")
            return None

    stack = await get_item(location, user_id, count=1)
    await give_item(user_id, stack)
    item_name = await stack.getName()
    logger.info(f"Sign gift drop: user={user_id}, gift={gift_id}")
    return gift_id, item_name


async def _get_hitokoto(user_id: str) -> str:
    try:
        if (count := await get_unread_email_count(user_id)) > 0:
            return await lang.text("image.email_unread", user_id, count)
        async with httpx.AsyncClient() as client:
            response = await client.get(config.hitokoto_api)
        if response.status_code == 200:
            return response.json()["hitokoto"]
        return await lang.text("image.hitokoto", user_id)
    except Exception as e:
        logger.exception(e)
        return await lang.text("image.hitokoto", user_id)


async def _calc_sign_exp(
    user_id: str, sign_days: int
) -> dict:
    """计算并增加签到经验值。返回 (text, origin, add, now)。"""
    user = await get_user(user_id)
    level = user.get_level()
    origin_exp = user.get_experience()
    exp = round(random.random() * level / 2 * max(user.get_fav(), 0.1) * min(sign_days + 1, 15) + 1)
    if level <= 4:
        exp = round(exp * 1.3)
    await user.add_experience(exp)
    return {
        "text": await lang.text("image.exp", user_id),
        "now": user.get_experience(),
        "add": exp,
        "origin": origin_exp,
    }


async def _calc_sign_vim(
    user_id: str, sign_days: int
) -> dict:
    """计算并增加签到虚拟币。返回 (text, origin, add, now)。"""
    user = await get_user(user_id)
    level = user.get_level()
    origin = user.get_vimcoin()
    vim = round(
        1
        + math.sqrt(
            math.sqrt(
                (1000 + random.random()) * level * max(user.get_fav(), 0.1) / 5 * min(sign_days, 15) / 8
                + 1
            )
        )
        * 25
        * random.random(),
        1,
    )
    await user.add_vimcoin(vim)
    return {
        "text": await lang.text("image.vim", user_id),
        "add": vim,
        "origin": origin,
        "now": user.get_vimcoin(),
    }


async def _calc_sign_fav(user_id: str) -> dict:
    """计算并增加签到好感度。返回 (text, origin, add, now)。"""
    user = await get_user(user_id)
    origin = user.get_display_fav()
    fav = 0.001
    await user.add_fav(fav)
    return {
        "text": await lang.text("image.fav", user_id),
        "add": round(fav * 1000),
        "now": user.get_display_fav(),
        "origin": origin,
    }


async def _is_user_signed(user_id: str) -> bool:
    async with get_session() as session:
        data = await _get_sign_data(session, user_id)
        return (date.today() - data.last_sign).days < 1


class SignHandler:
    """签到处理类：数据操作与渲染分离"""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._already_signed: bool = False
        self._final_sign_days: int = 0
        self._rank: int = 0
        self._gift_text: Optional[str] = None
        self._templates: dict = {}
        self._bg_kwargs: dict = {}

    async def process_data(self) -> None:
        """收集信息并操作数据（SignData 表操作由全局锁保护）"""

        # ====== Phase 1: 预检查 ======
        async with get_session() as session:
            data = await _get_sign_data(session, self.user_id)

        if (date.today() - data.last_sign).days < 1:
            self._already_signed = True
            return

        # ====== Phase 2: 判断补签（涉及用户交互，不可放锁内） ======
        days_since = (date.today() - data.last_sign).days
        self._do_resign = False
        self._missed_days = 0
        if days_since > 1:
            self._missed_days = days_since - 1
            if self._missed_days < 15:
                user = await get_user(self.user_id)
                needed = self._missed_days * 30
                if await user.has_vimcoin(needed):
                    try:
                        self._do_resign = await prompt(
                            await lang.text("resign.prompt", self.user_id, self._missed_days, needed),
                            self.user_id,
                            retry=1,
                            parser=lambda message: not message.lower().startswith("n"),
                            ignore_error_details=False,
                            allow_quit=False,
                        )
                    except (PromptTimeout, PromptRetryTooMuch):
                        pass

        # ====== Phase 3: 全局锁保护——操作 SignData 表 ======
        async with _global_sign_lock:
            async with get_session() as session:
                sd = await session.get_one(SignData, {"user_id": self.user_id})
                if (date.today() - sd.last_sign).days < 1:
                    self._already_signed = True
                    return

                # 计算新签到天数
                if days_since == 1:
                    sd.sign_days += 1
                elif self._do_resign:
                    sd.sign_days += self._missed_days + 1  # 补签天数 + 当天
                else:
                    sd.sign_days = 1
                self._final_sign_days = sd.sign_days

                # 排名（基于当前已签到人数）
                signed_today = (
                    await session.execute(
                        select(SignData.user_id).where(SignData.last_sign == date.today())
                    )
                ).scalars().all()
                self._rank = len(signed_today) + 1

                # 第一名礼物掉落
                if self._rank == 1:
                    gift = await _try_sign_gift_drop(self.user_id)
                    if gift:
                        self._gift_text = gift[1]

                sd.last_sign = date.today()
                await session.commit()

        # ====== Phase 4: 补签奖励（用户数据，不涉及 SignData 锁） ======
        if self._do_resign:
            got_vim = 0.0
            got_exp = 0
            # 每日补签奖励：逐天累加
            for offset in range(self._missed_days):
                day_count = offset + 1  # 第一天从 1 开始计
                got_vim += (await _calc_sign_vim(self.user_id, day_count))["add"]
                got_exp += (await _calc_sign_exp(self.user_id, day_count))["add"]
            user = await get_user(self.user_id)
            await user.add_fav(0.001 * self._missed_days)
            await lang.send(
                "resign.success",
                self.user_id,
                self._missed_days,
                round(got_vim, 1),
                got_exp,
            )

    async def render_result(self, matcher: Matcher) -> None:
        """渲染并发送处理结果"""
        if self._already_signed:
            await lang.finish("sign.signed", self.user_id)

        self._templates = {
            "date": date.today().strftime("%d"),
            "signdays": {
                "text": await lang.text("image.signdays", self.user_id),
                "value": await lang.text(
                    "image.signdays_text",
                    self.user_id,
                    self._final_sign_days,
                ),
            },
            "rank": {
                "text": await lang.text("image.rank", self.user_id),
                "value": await lang.text("image.rank_text", self.user_id, self._rank),
            },
            "exp": await _calc_sign_exp(self.user_id, self._final_sign_days),
            "vim": await _calc_sign_vim(self.user_id, self._final_sign_days),
            "fav": await _calc_sign_fav(self.user_id),
            "fortune": {
                "text": await lang.text("image.fortune", self.user_id),
                "value": await lang.text(f"luck.{await _get_luck(self.user_id)}", self.user_id),
            },
            "hitokoto": (
                await lang.text("image.gift", self.user_id, self._gift_text)
                if self._gift_text
                else await _get_hitokoto(self.user_id)
            ),
        }
        user = await get_user(self.user_id)
        self._templates["nickname"] = user.nickname
        self._templates["uid"] = await lang.text("image.uid", self.user_id, self.user_id)
        self._templates["avatar"] = (
            base64.b64encode(user.avatar).decode() if user.avatar is not None else None
        )

        # 横版 setu 背景
        try:
            setu_img = await get_landscape_image()
            if setu_img:
                b64 = base64.b64encode(setu_img["image"]).decode()
                ext = setu_img["data"].ext
                self._bg_kwargs["background_url"] = (
                    f"data:image/png;base64,{b64}" if ext == "png" else f"data:image/jpeg;base64,{b64}"
                )
        except Exception as e:
            logger.warning(f"获取 setu 背景图失败: {e}")

        image = await render_template(
            "sign.html.jinja",
            await lang.text("image.title", self.user_id),
            self.user_id,
            self._templates,
            viewport={"width": 380, "height": 10},
            **self._bg_kwargs,
        )
        msg = UniMessage().image(raw=image)
        await matcher.finish(await msg.export(), at_sender=True)


@sign.handle()
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    handler = SignHandler(user_id)
    await handler.process_data()
    await handler.render_result(matcher)


# 暴露给外部使用的接口
is_user_signed = _is_user_signed
