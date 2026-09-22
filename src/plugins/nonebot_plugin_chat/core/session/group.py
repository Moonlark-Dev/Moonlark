from typing import Literal, Optional, cast

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_chat.config import config
from nonebot_plugin_chat.types import AdapterUserInfo
from nonebot_plugin_ghot.function import get_group_hot_score
from nonebot_plugin_larkuser import (
    ensure_group_members,
    get_group_member,
    get_group_member_nickname_map,
    get_group_name,
    get_user,
)

from .base import BaseSession


import asyncio
import re
from datetime import datetime, timedelta


class GroupSession(BaseSession):

    @staticmethod
    def get_session_type() -> Literal["group"]:
        return "group"

    async def get_user_info(self, user_id: str) -> AdapterUserInfo:
        if isinstance(self.bot, OB11Bot):
            member_info = await self.bot.get_group_member_info(
                group_id=int(self.adapter_group_id), user_id=int(user_id)
            )
            adapter_nickname = member_info["nickname"]
            user = await get_user(user_id)
            return AdapterUserInfo(
                **member_info,
                nickname=adapter_nickname if not user.has_nickname() else user.get_nickname(),
            )
        if isinstance(self.bot, QQBot):
            member = await get_group_member(self.adapter_group_id, user_id)
            if member is not None:
                user = await get_user(user_id)
                return AdapterUserInfo(
                    nickname=member.nickname if not user.has_nickname() else user.get_nickname(),
                    sex="unknown",
                    role=member.role if member.role in ("member", "admin", "owner") else "member",
                    join_time=int(member.joined_at.timestamp()) if member.joined_at else 0,
                    card=None,
                )
        cached_users = await self.get_users()
        if user_id in cached_users.values():
            for nickname, uid in cached_users.items():
                if uid == user_id:
                    return AdapterUserInfo(nickname=nickname, sex="unknown", role="member", join_time=0, card=None)
        return AdapterUserInfo(
            nickname=(await get_user(user_id)).get_nickname(), sex="unknown", role="member", join_time=0, card=None
        )

    async def _get_ob11_group_users(self) -> dict[str, str]:
        """通过 OneBot 11 接口获取「昵称 -> 用户 ID」映射"""
        bot = cast(OB11Bot, self.bot)
        users: dict[str, str] = {}
        for user in await bot.get_group_member_list(group_id=int(self.adapter_group_id)):
            adapter_nickname = user["nickname"]
            ml_user = await get_user(str(user["user_id"]))
            nickname = adapter_nickname if not ml_user.has_nickname() else ml_user.get_nickname()
            users[nickname] = str(user["user_id"])
        return users

    async def _get_qq_group_users(self) -> dict[str, str]:
        """通过 QQ 官方 Bot 的群成员列表（缓存）获取「昵称 -> 成员 openid」映射"""
        users = await get_group_member_nickname_map(self.adapter_group_id)
        if users:
            return users
        # 缓存尚未建立时同步一次，失败则由调用方回退到消息缓存
        await ensure_group_members(cast(QQBot, self.bot), self.adapter_group_id)
        return await get_group_member_nickname_map(self.adapter_group_id)

    async def get_users(self) -> dict[str, str]:
        cached_users = await self._get_users_in_cached_message()
        if any([u not in self.group_users for u in cached_users.keys()]):
            if isinstance(self.bot, OB11Bot):
                self.group_users = await self._get_ob11_group_users()
            elif isinstance(self.bot, QQBot):
                # 与 OneBot 11 一致，@ 解析以群成员列表为准，取不到时回退到消息缓存
                qq_users = await self._get_qq_group_users()
                self.group_users = qq_users if qq_users else {**self.group_users, **cached_users}
            else:
                self.group_users = cached_users
        return self.group_users

    def __init__(self, session_id: str, bot: Bot, target: Target, lang_name: str = "zh_hans") -> None:
        lang_str = f"mlsid::--lang={lang_name}"
        super().__init__(session_id, bot, target, lang_str)
        self.adapter_group_id = target.id
        self.cached_latest_message = None

    async def setup(self) -> None:
        await super().setup()
        await self.calculate_ghot_coefficient()

    async def send_poke(self, target_id: str) -> None:
        await self.bot.call_api("group_poke", group_id=int(self.adapter_group_id), user_id=int(target_id))

    def is_napcat_bot(self) -> bool:
        return self.bot.self_id in config.napcat_bot_ids

    async def calculate_ghot_coefficient(self) -> None:
        self.ghot_coefficient = round(max((10 - (await get_group_hot_score(self.session_id))[2]), 1))
        cached_users = set()
        for message in self.cached_messages[:-5]:
            if not message["self"]:
                cached_users.add(message["user_id"])
        if len(cached_users) <= 1:
            self.ghot_coefficient *= 0.75

    async def get_session_name(self) -> Optional[str]:
        if isinstance(self.bot, OB11Bot):
            return (await self.bot.get_group_info(group_id=int(self.adapter_group_id)))["group_name"]
        if isinstance(self.bot, QQBot):
            return await get_group_name(self.bot, self.adapter_group_id)
        return None

    async def format_message(self, origin_message: str) -> UniMessage:
        message = re.sub(r"\[\d\d:\d\d:\d\d]\[Moonlark]\(\d+\): ?", "", origin_message)
        message = message.strip()
        users = await self.get_users()
        if not users:
            # 没有任何已知成员时直接返回，避免空正则匹配到每个字符
            return UniMessage().text(text=message)
        uni_msg = UniMessage()
        at_list = re.finditer("|".join([f"@{re.escape(user)}" for user in users.keys()]), message)
        cursor_index = 0
        for at in at_list:
            uni_msg = uni_msg.text(text=message[cursor_index : at.start()])
            at_nickname = at.group(0)[1:]
            if user_id := users.get(at_nickname):
                uni_msg = uni_msg.at(user_id)
            else:
                uni_msg = uni_msg.text(at.group(0))
            cursor_index = at.end()
        uni_msg = uni_msg.text(text=message[cursor_index:])
        return uni_msg

    async def process_timer(self) -> None:
        await super().process_timer()
        # 定期确保 system prompt 存在（防止意外丢失）
        await self.processor.openai_messages._ensure_system_prompt()
        dt = datetime.now()
        if self.message_queue or self.processor.blocked or not self.cached_messages:
            return
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        wait_threshold = max(15, 60 - (await get_group_hot_score(self.session_id))[2])
        recent_message_count = len(
            [msg for msg in self.cached_messages if (dt - msg["send_time"]) < timedelta(minutes=5)]
        )
        if (
            wait_threshold < time_to_last_message
            and not self.cached_messages[-1]["self"]
            and self.cached_messages[-1] is not self.cached_latest_message
            and recent_message_count < 26
        ):
            self.cached_latest_message = self.cached_messages[-1]
            # 冷群检测触发，增加 0.3 token
            self.processor.token_bucket.add(1)
            asyncio.create_task(self.processor.generate_reply())
