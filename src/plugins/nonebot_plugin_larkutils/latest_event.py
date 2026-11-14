from typing import Optional

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import UniMessage


class LatestEvent:
    """跟踪连续交互中的最新事件，并向该事件发送消息。

    QQ 官方机器人要求被动回复绑定到具体的用户消息事件，且同一条消息的被动回复
    次数存在上限。连续交互的指令如果始终通过 ``matcher.send`` 回复最初触发指令的
    那条事件，回复几条之后就会因为超过上限而发送失败。

    每次等待输入后，把 waiter 记录的最新事件通过 :meth:`update` 交回本对象，
    后续提示、失败信息与结算结果都通过 :meth:`send` 显式回复到最新事件。
    """

    def __init__(self, event: Optional[Event] = None, bot: Optional[Bot] = None) -> None:
        self.event = event
        self.bot = bot

    def update(self, event: Optional[Event]) -> None:
        """更新为最新收到的事件；传入 ``None`` 时保留原事件。"""
        if event is not None:
            self.event = event

    async def send(self, message: str | UniMessage, at_sender: bool = False) -> None:
        """向最新事件发送消息。"""
        if isinstance(message, str):
            message = UniMessage(message)
        await message.send(target=self.event, bot=self.bot, at_sender=at_sender)
