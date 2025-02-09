from typing import Optional
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from nonebot import on_message
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
    ) -> None:
        self.prompt_text = prompt_text
        self.user_id = ""
        self.session_id = session_id
        self.default = default
        self.checker = lambda _: True
        self.answer = None
        self.message_matcher = on_message(block=True, rule=checker)
        self.message_matcher.handle()(self.handle_message)

    async def handle_message(self, matcher: Matcher, event: Event, user_id: str = get_user_id()) -> None:
        self.user_id = user_id
        return await super().handle_message(matcher, event, user_id)

    def check_group(self, group_id: str = get_group_id()) -> bool:
        return group_id == self.session_id
