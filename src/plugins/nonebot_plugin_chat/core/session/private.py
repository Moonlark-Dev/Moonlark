from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_chat.config import config
from nonebot_plugin_chat.types import AdapterUserInfo
from nonebot_plugin_larkuser import get_user

from .base import BaseSession


class PrivateSession(BaseSession):

    def __init__(self, session_id: str, bot: Bot, target: Target) -> None:
        super().__init__(session_id, bot, target, lang_str=session_id)
        self.nickname = ""
        self.call = "你"
        self.user_info: AdapterUserInfo

    async def setup(self) -> None:
        await super().setup()
        await self.setup_session_name()

    async def setup_session_name(self) -> None:
        ml_user = await get_user(self.session_id)
        if isinstance(self.bot, OB11Bot):
            user_info = await self.bot.get_stranger_info(user_id=int(self.session_id))
            if ml_user.has_nickname():
                self.nickname = ml_user.get_nickname()
            else:
                self.nickname = user_info["nickname"]
            self.user_info = AdapterUserInfo(
                nickname=self.nickname, sex=user_info["sex"], role="user", join_time=0, card=None
            )
        else:
            self.nickname = ml_user.get_nickname()
            self.user_info = AdapterUserInfo(nickname=self.nickname, sex="unknown", role="user", join_time=0, card=None)
        self.call = ml_user.get_config_key("call", self.nickname)
        self.session_name = f"与 {self.nickname} 的私聊"

    async def format_message(self, origin_message: str) -> UniMessage:
        return UniMessage().text(text=origin_message.replace(f"@{self.nickname}", self.call))

    def is_napcat_bot(self) -> bool:
        return self.bot.self_id in config.napcat_bot_ids

    async def send_poke(self, _: str) -> None:
        if isinstance(self.bot, OB11Bot):
            await self.bot.call_api("friend_poke", user_id=self.session_id)

    async def calculate_ghot_coefficient(self) -> int:
        self.ghot_coefficient = 100
        return 100

    async def get_user_info(self, _: str) -> AdapterUserInfo:
        return self.user_info

    async def get_users(self) -> dict[str, str]:
        return {self.nickname: self.session_id}
