import asyncio
import base64
import math
import random
from datetime import date
from typing import Any, Optional

import httpx
from nonebot import logger, on_type
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq.bot import Bot as QQBot
from nonebot.adapters.qq.event import InteractionCreateEvent
from nonebot.adapters.qq.message import Message
from nonebot.exception import FinishedException
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Alconna, Args, Subcommand, UniMessage, on_alconna
from nonebot_plugin_bag.models import Bag
from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_email.utils.unread import get_unread_email_count
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_larksetu import get_landscape_image
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.user.utils import is_user_registered
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkuser.utils.register import register_user
from nonebot_plugin_alconna import Button
from nonebot_plugin_larkuser.utils.waiter import PromptRetryTooMuch, PromptTimeout, prompt
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.cache import create_image_markdown
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_orm import AsyncSession, get_session
from nonebot_plugin_render.render import render_template
from nonebot_plugin_userinfo import get_user_info
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from .config import config
from .lang import lang
from .models import SignData

alc = Alconna(
    "签到",
    Subcommand("auto", Args["action?", ["on", "off", "limit"]], Args["limit?", int]),
)
sign = on_alconna(alc, aliases={"签到", "sign"})
patch_matcher(sign)

# 全局锁，保护 SignData 数据操作
_global_sign_lock = asyncio.Lock()

# 自动签到券物品 ID 与连续签到奖励周期（天）
AUTO_SIGN_TICKET_ID = "moonlark:auto_sign_ticket"
AUTO_SIGN_TICKET_REWARD_DAYS = 5


def get_auto_sign_ticket_location() -> ResourceLocation:
    return get_location_by_id(AUTO_SIGN_TICKET_ID)


async def get_auto_sign_ticket_count(user_id: str) -> int:
    """获取用户背包中自动签到券的数量"""
    async with get_session() as session:
        count = await session.scalar(
            select(func.sum(Bag.count)).where(
                Bag.user_id == user_id,
                Bag.item_id == AUTO_SIGN_TICKET_ID,
            ),
        )
    return count or 0


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


async def _calc_sign_exp(user_id: str, sign_days: int) -> dict:
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


async def _calc_sign_vim(user_id: str, sign_days: int) -> dict:
    """计算并增加签到虚拟币。返回 (text, origin, add, now)。"""
    user = await get_user(user_id)
    level = user.get_level()
    origin = user.get_vimcoin()
    vim = round(
        1
        + math.sqrt(
            math.sqrt((1000 + random.random()) * level * max(user.get_fav(), 0.1) / 5 * min(sign_days, 15) / 8 + 1)
        )
        * 25
        * random.random(),
        1,
    )
    await user.add_vimcoin(vim)
    return {
        "text": await lang.text("image.vim", user_id),
        "add": round(vim, 1),
        "origin": round(origin, 1),
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


async def _give_auto_sign_tickets(user_id: str, count: int) -> None:
    """向用户发放自动签到券"""
    item = await get_item(get_auto_sign_ticket_location(), user_id, count, {})
    await give_item(user_id, item)


async def perform_sign(user_id: str, missed_days: int = 0, auto: bool = False) -> Optional[dict[str, Any]]:
    """执行签到：更新 SignData 并按正常流程发放奖励（不包含补签询问与结果渲染）

    Args:
        user_id (str): 用户 ID
        missed_days (int, optional): 补签天数，仅普通签到的补签流程会传入. Defaults to 0.
        auto (bool, optional): 是否为自动签到（累计自动签到数据）. Defaults to False.

    Returns:
        Optional[dict[str, Any]]: 签到结果；当天已签到时返回 None
    """
    do_resign = missed_days > 0

    # ====== 全局锁保护——操作 SignData 表 ======
    async with _global_sign_lock:
        async with get_session() as session:
            sd = await _get_sign_data(session, user_id)
            days_since = (date.today() - sd.last_sign).days
            if days_since < 1:
                return None

            # 计算新签到天数
            if days_since == 1:
                sd.sign_days += 1
            elif do_resign:
                sd.sign_days += missed_days + 1  # 补签天数 + 当天
            else:
                sd.sign_days = 1
            final_sign_days = sd.sign_days

            # 自动签到计数
            if auto:
                sd.auto_count += 1
                sd.auto_used += 1

            # 排名（基于当前已签到人数）
            signed_today = (
                (await session.execute(select(SignData.user_id).where(SignData.last_sign == date.today())))
                .scalars()
                .all()
            )
            rank = len(signed_today) + 1

            sd.last_sign = date.today()
            await session.commit()

    # ====== 当天奖励（用户数据，不涉及 SignData 锁） ======
    exp = await _calc_sign_exp(user_id, final_sign_days)
    vim = await _calc_sign_vim(user_id, final_sign_days)
    fav = await _calc_sign_fav(user_id)

    # ====== 补签奖励：逐天累加 ======
    resign_result = None
    if do_resign:
        got_vim = 0.0
        got_exp = 0
        for offset in range(missed_days):
            day_count = offset + 1  # 第一天从 1 开始计
            got_vim += (await _calc_sign_vim(user_id, day_count))["add"]
            got_exp += (await _calc_sign_exp(user_id, day_count))["add"]
        user = await get_user(user_id)
        await user.add_fav(0.001 * missed_days)
        resign_result = {"days": missed_days, "vim": round(got_vim, 1), "exp": got_exp}

    # ====== 连续签到奖励：每连续签到 5 天奖励一张自动签到券 ======
    ticket_gained = 0
    if final_sign_days % AUTO_SIGN_TICKET_REWARD_DAYS == 0:
        ticket_gained = 1
        await _give_auto_sign_tickets(user_id, ticket_gained)

    return {
        "sign_days": final_sign_days,
        "rank": rank,
        "exp": exp,
        "vim": vim,
        "fav": fav,
        "ticket_gained": ticket_gained,
        "resign": resign_result,
    }


class SignHandler:
    """签到处理类：数据操作与渲染分离"""

    def __init__(self, user_id: str, bot: Bot, event: Event, matcher: Matcher) -> None:
        self.user_id = user_id
        self.bot = bot
        self.event = event
        self._result: Optional[dict[str, Any]] = None
        self.matcher = matcher
        self._do_resign: bool = False
        self._missed_days: int = 0
        self._templates: dict = {}
        self._bg_kwargs: dict = {}

    async def process_register(self) -> None:
        """判断用户是否注册，如果未注册就触发注册流程。"""
        bot = self.bot
        event = self.event
        user = await get_user(self.user_id)
        if not user.is_registered():
            if not (user_info := await get_user_info(bot, event, self.user_id)):
                await lang.finish("sign.get_userinfo_failed", self.user_id)
            async with get_session() as session:
                await register_user(session, self.user_id, user_info)

    async def process_data(self) -> None:
        """收集信息并操作数据（SignData 表操作由全局锁保护）"""

        await self.process_register()

        # ====== Phase 1: 预检查 ======
        if await _is_user_signed(self.user_id):
            return

        # ====== Phase 2: 判断补签（涉及用户交互，不可放锁内） ======
        async with get_session() as session:
            data = await _get_sign_data(session, self.user_id)
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

        # ====== Phase 3+4: 签到数据操作与奖励发放 ======
        self._result = await perform_sign(self.user_id, self._missed_days if self._do_resign else 0)
        if self._result is not None and (resign := self._result["resign"]):
            await lang.send(
                "resign.success",
                self.user_id,
                resign["days"],
                resign["vim"],
                resign["exp"],
            )

    async def render_result(self) -> None:
        """渲染并发送处理结果

        Args:
            matcher: Nonebot 匹配器
            invite_button: 是否附带"我也要签到"按钮（仅 QQ 官方机器人）
        """
        if self._result is None:
            await lang.finish("sign.signed", self.user_id)

        self._templates = {
            "date": date.today().strftime("%d"),
            "signdays": {
                "text": await lang.text("image.signdays", self.user_id),
                "value": await lang.text(
                    "image.signdays_text",
                    self.user_id,
                    self._result["sign_days"],
                ),
            },
            "rank": {
                "text": await lang.text("image.rank", self.user_id),
                "value": await lang.text("image.rank_text", self.user_id, self._result["rank"]),
            },
            "exp": self._result["exp"],
            "vim": self._result["vim"],
            "fav": self._result["fav"],
            "fortune": {
                "text": await lang.text("image.fortune", self.user_id),
                "value": await lang.text(f"luck.{await _get_luck(self.user_id)}", self.user_id),
            },
            "hitokoto": await _get_hitokoto(self.user_id),
        }
        if self._result["ticket_gained"]:
            self._templates["ticket"] = {
                "text": await lang.text("image.ticket", self.user_id),
                "value": await lang.text("image.ticket_text", self.user_id, self._result["ticket_gained"]),
            }
        user = await get_user(self.user_id)
        self._templates["nickname"] = user.nickname
        self._templates["uid"] = await lang.text("image.uid", self.user_id, self.user_id)
        self._templates["avatar"] = base64.b64encode(user.avatar).decode() if user.avatar is not None else None

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
            resize=True,
            **self._bg_kwargs,
        )
        await self.send_card(image)

    async def send_card(self, image: bytes) -> None:
        if isinstance(self.bot, QQBot):
            await self.format_markdown(image)
        else:
            msg = UniMessage().image(raw=image)
            await self.matcher.finish(await msg.export(), at_sender=True)

    async def format_markdown(self, image_raw: bytes) -> None:
        if self._result is None:
            await lang.finish("sign.signed", self.user_id)
        await (
            UniMessage()
            .style(
                f'<qqbot-at-user id="{self.event.get_user_id()}" />{await create_image_markdown(image_raw)}', "markdown"
            )
            .keyboard(await self.build_button())
            .send()
        )
        await self.matcher.finish()

    async def build_button(self) -> Button:
        return Button(
            "enter",
            await lang.text("button.invite", self.user_id),
            text=f"{config.command_start[0]}sign",
        )


@sign.assign("$main")
async def _(matcher: Matcher, bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    handler = SignHandler(user_id, bot, event, matcher)
    await handler.process_data()
    await handler.render_result()


async def _set_auto_sign(user_id: str, *, enabled: bool) -> None:
    """开启或关闭自动签到"""
    async with get_session() as session:
        data = await _get_sign_data(session, user_id)
        if data.auto_enabled == enabled:
            await lang.finish("auto.on_already" if enabled else "auto.off_already", user_id)
        data.auto_enabled = enabled
        await session.commit()
    await lang.finish("auto.on_done" if enabled else "auto.off_done", user_id)


async def _set_auto_sign_limit(user_id: str, limit: Optional[int]) -> None:
    """重置使用计数并设定允许使用的自动签到券个数（<= 0 为不限制）"""
    if limit is None:
        await lang.finish("auto.limit_usage", user_id)
    async with get_session() as session:
        data = await _get_sign_data(session, user_id)
        data.auto_limit = limit
        data.auto_used = 0
        await session.commit()
    if limit <= 0:
        await lang.finish("auto.limit_unlimited_done", user_id)
    await lang.finish("auto.limit_done", user_id, limit)


async def _show_auto_sign_status(user_id: str) -> None:
    """查看自动签到情况"""
    async with get_session() as session:
        data = await _get_sign_data(session, user_id)
        enabled, count, limit, used = data.auto_enabled, data.auto_count, data.auto_limit, data.auto_used
    tickets = await get_auto_sign_ticket_count(user_id)
    if limit <= 0:
        limit_text = await lang.text("auto.limit_unlimited", user_id)
    else:
        limit_text = await lang.text("auto.limit_text", user_id, limit, used)
    await lang.finish(
        "auto.status",
        user_id,
        status=await lang.text("auto.status_on" if enabled else "auto.status_off", user_id),
        count=count,
        tickets=tickets,
        limit=limit_text,
    )


@sign.assign("auto")
async def _(action: Optional[str] = None, limit: Optional[int] = None, user_id: str = get_user_id()) -> None:
    if action == "on":
        await _set_auto_sign(user_id, enabled=True)
    elif action == "off":
        await _set_auto_sign(user_id, enabled=False)
    elif action == "limit":
        await _set_auto_sign_limit(user_id, limit)
    else:
        await _show_auto_sign_status(user_id)


# 暴露给外部使用的接口
is_user_signed = _is_user_signed
