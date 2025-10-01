import pytest
from nonebug import App


@pytest.mark.asyncio
async def test_chat_message_parser(app: App):
    from nonebot_plugin_chat.utils.group import parse_message_to_string
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    # 转发
    message = Message()
