from typing import Literal

from ..types import Message, Messages


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
