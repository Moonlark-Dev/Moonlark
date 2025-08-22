#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot_plugin_orm import get_session
from typing import Literal

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, \
    ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam
from sqlalchemy import select

from ..types import Message, Messages


def generate_message(content: str | list, role: Literal["system", "user", "assistant"] = "system") -> Message:
    # NOTE 以下写法过不了类型检查
    # return {
    #     "role": role,
    #     "content": content
    # }
    if role == "system":
        return ChatCompletionSystemMessageParam(content=content, role="system")
    elif role == "user":
        return ChatCompletionUserMessageParam(content=content, role="user")
    elif role == "assistant":
        return ChatCompletionAssistantMessageParam(content=content, role="assistant")
    else:
        raise ValueError(f"Invalid role: {role}")


#
#
# async def get_session_messages(session_id: int) -> list[Message]:
#     async with get_session() as session:
#         result = await session.scalars(
#             select(SessionMessage).where(SessionMessage.session_id == session_id).order_by(SessionMessage.message_id)
#         )
#         return [generate_message(message.content.decode(), message.role) for message in result]
