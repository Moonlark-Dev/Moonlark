from typing import Optional
from nonebot.adapters import Event, Bot
from nonebot.matcher import Matcher
from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot.rule import Rule
from nonebot_plugin_alconna import UniMessage


class Waiter3(WaitUserInput):
    def __init__(
        self,
        prompt_text: UniMessage,
        session_id: str,
        checker: Rule,
        default: Optional[str] = None,
        event: Optional[Event] = None,
    ) -> None:
        self.session_id = session_id
        # 按群聊匹配候选单词；反馈消息始终回复用户最新消息，避免 QQ 被动回复超限
        super().__init__(
            prompt_text,
            "",
            default=default,
            event=event,
            rule=checker & Rule(self.check_session),
        )

    async def handle_message(self, matcher: Matcher, event: Event, bot: Bot, user_id: str = get_user_id()) -> None:
        self.user_id = user_id
        return await super().handle_message(matcher, event, bot, user_id)

    def check_session(self, group_id: str = get_group_id()) -> bool:
        return group_id == self.session_id
