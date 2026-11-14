"""消息构造与 prompt 模板渲染

模板目录与 OpenAI 插件一致（``./src/prompt``），渲染逻辑也保持一致，便于两个插件
共用同一套 prompt。
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader

from ..types import Message, Messages

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
    return {"role": role, "content": content}


async def get_message_text(name: str, **kwargs) -> str:
    template = env.get_template(name)
    # 只在未提供 current_time 时才使用当前时间
    if "current_time" not in kwargs:
        kwargs["current_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return await template.render_async(**kwargs)


async def get_message(role: Literal["system", "user", "assistant"], name: str, **kwargs) -> Message:
    text = await get_message_text(name, **kwargs)
    return generate_message(text, role)


async def get_messages(prefix: str, **kwargs) -> Messages:
    return [
        await get_message("system", f"{prefix}/system.md.jinja", **kwargs),
        await get_message("user", f"{prefix}/user.md.jinja", **kwargs),
    ]
