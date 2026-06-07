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

from datetime import datetime

from nonebot_plugin_orm import get_session
from typing import Any, Literal

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
)
from sqlalchemy import select

from ..types import Message, Messages

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

file_loader = FileSystemLoader(Path("./src/prompt"))
env = Environment(
    loader=file_loader,
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    enable_async=True,
)



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

async def get_message_text(name: str, **kwargs) -> str:
    template = env.get_template(name)
    kwargs["current_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return await template.render_async(**kwargs)

async def get_message(role: Literal["system", "user", "assistant"], name: str, **kwargs) -> Message:
    text = await get_message_text(name, **kwargs)
    return generate_message(text, role)


async def get_messages(prefix: str, **kwargs) -> Messages:
    messages = [
        await get_message("system", f"{prefix}/system.md.jinja", **kwargs),
        await get_message("user", f"{prefix}/user.md.jinja", **kwargs),
    ]
    return messages
