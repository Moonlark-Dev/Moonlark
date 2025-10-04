# ref: https://github.com/nonebot/plugin-alconna/blob/master/tests/fake.py

from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import GroupMessageEvent


_msg_ids = iter(range(1000000))


def get_msg_id() -> int:
    return next(_msg_ids)


def fake_group_message_event_v11(**field) -> "GroupMessageEvent":
    from pydantic import create_model
    from nonebot.adapters.onebot.v11.event import Sender
    from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent

    _fake = create_model("_fake", __base__=GroupMessageEvent)

    class FakeEvent(_fake):
        time: int = 1000000
        self_id: int = 1
        post_type: Literal["message"] = "message"
        sub_type: str = "normal"
        user_id: int = 10
        message_type: Literal["group"] = "group"
        group_id: int = 10000
        message: Message = Message("test")
        raw_message: str = "test"
        font: int = 0
        sender: Sender = Sender(
            card="",
            nickname="test",
            role="member",
        )
        to_me: bool = False

        class Config:
            extra = "allow"

    return FakeEvent(message_id=get_msg_id(), **field)
