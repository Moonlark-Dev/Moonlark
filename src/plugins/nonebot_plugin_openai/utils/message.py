from nonebot_plugin_orm import get_session
from typing import Literal
from sqlalchemy import select

from ..types import Message, Messages
from ..models import SessionMessage

def generate_message(content: str, role: Literal["system", "user", "assistant"] = "system") -> Message:
    # NOTE 以下写法过不了类型检查
    # return {
    #     "role": role,
    #     "content": content
    # }
    if role == "system":
        return {"role": "system", "content": content}
    elif role == "user":
        return {"role": "user", "content": content}
    elif role == "assistant":
        return {"role": "assistant", "content": content}
    else:
        raise ValueError(f"Invalid role: {role}")


async def get_session_messages(session_id: int) -> list[Message]:
    async with get_session() as session:
        result = await session.scalars(select(SessionMessage).where(SessionMessage.session_id == session_id).order_by(SessionMessage.message_id))
        return [generate_message(message.content.decode(), message.role) for message in result]
