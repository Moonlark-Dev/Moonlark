from unittest.mock import AsyncMock, patch

import pytest
from nonebug import App

from nonebot.adapters.onebot.v11 import Bot, Message
from fake import fake_group_message_event_v11


@pytest.fixture
async def blocked_user(app: App):
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_access.models import SubjectData

    async with get_session() as session:
        session.add(SubjectData(subject="1619365833", name="plugin_nonebot_plugin_bag", available=False))
        await session.commit()


@pytest.mark.asyncio
async def test_bag_command_sends_single_permission_message(app: App, blocked_user):
    from nonebot_plugin_bag.__main__ import bag

    send = AsyncMock(return_value=1)

    with (
        patch("nonebot_plugin_alconna.uniseg.message.UniMessage.send", send),
        patch("nonebot_plugin_auto_bind.main.get_user_info", AsyncMock(return_value=None)),
    ):
        async with app.test_matcher(bag) as ctx:
            bot = ctx.create_bot(base=Bot, self_id="1")
            event = fake_group_message_event_v11(user_id=1619365833, group_id=10000, message=Message("bag"))
            ctx.receive_event(bot, event)
        assert send.await_count == 1, f"期望 1 条权限失败提示，实际 {send.await_count}"
