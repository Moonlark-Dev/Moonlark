from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_chat.config import config
from nonebot_plugin_chat.types import AdapterUserInfo
from nonebot_plugin_ghot.function import get_group_hot_score
from nonebot_plugin_larkuser import get_user

from .base import BaseSession


import asyncio
import re
from datetime import datetime


class GroupSession(BaseSession):

    async def get_user_info(self, user_id: str) -> AdapterUserInfo:
        if isinstance(self.bot, OB11Bot):
            member_info = await self.bot.get_group_member_info(
                group_id=int(self.adapter_group_id), user_id=int(user_id)
            )
            return AdapterUserInfo(**member_info)
        cached_users = await self.get_users()
        if user_id in cached_users.values():
            for nickname, uid in cached_users.items():
                if uid == user_id:
                    return AdapterUserInfo(nickname=nickname, sex="unknown", role="member", join_time=0, card=None)
        return AdapterUserInfo(
            nickname=(await get_user(user_id)).get_nickname(), sex="unknown", role="member", join_time=0, card=None
        )

    async def get_users(self) -> dict[str, str]:
        cached_users = await self._get_users_in_cached_message()
        if any([u not in self.group_users for u in cached_users.keys()]):
            if isinstance(self.bot, OB11Bot):
                self.group_users.clear()
                for user in await self.bot.get_group_member_list(group_id=int(self.adapter_group_id)):
                    self.group_users[user["nickname"]] = str(user["user_id"])
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
        await self.setup_session_name()
        await self.calculate_ghot_coefficient()

    async def send_poke(self, target_id: str) -> None:
        await self.bot.call_api("group_poke", group_id=int(self.adapter_group_id), user_id=int(target_id))

    def is_napcat_bot(self) -> bool:
        return self.bot.self_id in config.napcat_bot_ids

    async def calculate_ghot_coefficient(self) -> None:
        self.ghot_coefficient = round(max((15 - (await get_group_hot_score(self.session_id))[2]) * 0.8, 1))
        cached_users = set()
        for message in self.cached_messages[:-5]:
            if not message["self"]:
                cached_users.add(message["user_id"])
        if len(cached_users) <= 1:
            self.ghot_coefficient *= 0.75

    async def setup_session_name(self) -> None:
        if isinstance(self.bot, OB11Bot):
            self.session_name = (await self.bot.get_group_info(group_id=int(self.adapter_group_id)))["group_name"]

    async def format_message(self, origin_message: str) -> UniMessage:
        message = re.sub(r"\[\d\d:\d\d:\d\d]\[Moonlark]\(\d+\): ?", "", origin_message)
        message = message.strip()
        users = await self.get_users()
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
        dt = datetime.now()
        if self.processor.blocked or not self.cached_messages:
            return
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        if (
            30 < time_to_last_message
            and not self.cached_messages[-1]["self"]
            and self.cached_messages[-1] is not self.cached_latest_message
        ):
            self.cached_latest_message = self.cached_messages[-1]
            asyncio.create_task(self.processor.generate_reply(important=True))