"""OpenAI 风格消息到 Gemini Content 的转换

Moonlark 的各插件（尤其是 Chat）内部一直使用 OpenAI 的消息结构：

- ``{"role": "system" | "user" | "assistant", "content": str | list[part]}``
- 工具调用：assistant 消息带 ``tool_calls``，工具返回是 ``{"role": "tool", "tool_call_id": ...}``
- 多模态：``{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}``

Gemini SDK 需要的是 ``types.Content(role="user" | "model", parts=[...])``，并且把
system 消息放在 ``system_instruction`` 里。本模块负责这层转换，使调用方可以在两个
SDK 之间原样切换消息列表：

- system 消息合并成 ``system_instruction``；
- 文本 / data URL 图片分别转成 ``text`` / ``inline_data`` part；
- assistant 的 ``tool_calls`` 转成 ``function_call`` part，工具返回的 tool 消息转成
  紧跟在后的 ``function_response`` part（Gemini 通过函数名匹配，因此这里会先扫描
  assistant 消息建立 call id -> 函数名 的映射）；
- 相邻同角色消息合并成一个 Content（Gemini 不要求严格交替，但合并后请求更小、更稳定）。

Gemini 3 的函数调用会带 ``thought_signature``，历史消息里缺少它可能被拒绝。我们把
它作为额外字段塞进 OpenAI 风格的 ``tool_calls`` 条目（``thought_signature``，base64），
Chat 的上下文会原样保存这个 dict，于是跨请求回放时签名不会丢失；发给 OpenAI 之前由
那边剔除不认识的字段。
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Optional

from google.genai import types
from nonebot.log import logger

from ..types import Message, Messages

# 存放在 OpenAI 风格 tool_calls 条目里的 thought_signature 字段名（base64 字符串）
THOUGHT_SIGNATURE_KEY = "thought_signature"


def _clean_text(text: str) -> str:
    """剔除 NUL（U+0000）：网关会把含它的请求体整次写成 {"message": "invalid text"}"""
    return text.replace("\x00", "") if "\x00" in text else text


def _message_role(message: Message) -> str:
    return str(message.get("role") or "")


def _content(message: Message) -> Any:
    return message.get("content")


def _text_of(content: Any) -> str:
    """把 content 中所有文本 part 拼成一段文本（用于 system 消息等纯文本场景）"""
    if content is None:
        return ""
    if isinstance(content, str):
        return _clean_text(content)
    texts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                texts.append(_clean_text(text))
    return "\n".join(texts)


def decode_data_url(url: Any) -> Optional[tuple[bytes, str]]:
    """解析 ``data:<mime>;base64,<payload>``，返回 (图片数据, MIME 类型)"""
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    header, separator, payload = url.partition(",")
    if not separator or ";base64" not in header:
        return None
    mime_type = header[5:].split(";")[0] or "application/octet-stream"
    try:
        return base64.b64decode(payload, validate=True), mime_type
    except (ValueError, binascii.Error):
        logger.warning("Gemini 转换消息时跳过无法解码的 base64 图片")
        return None


def is_image_part(part: Any) -> bool:
    """判断内容块是否为图片块（OpenAI 风格 image_url）"""
    return isinstance(part, dict) and part.get("type") == "image_url"


def image_part_indices(content: Any) -> list[int]:
    """返回 content 中所有图片块的下标"""
    if not isinstance(content, list):
        return []
    return [index for index, part in enumerate(content) if is_image_part(part)]


def _image_url_of(part: dict[str, Any]) -> Any:
    image_url = part.get("image_url")
    if isinstance(image_url, dict):
        return image_url.get("url")
    return image_url


def content_parts(content: Any) -> list[types.Part]:
    """把消息 content 转换成 Gemini 的 Part 列表"""
    if content is None:
        return []
    if isinstance(content, str):
        return [types.Part(text=_clean_text(content))] if content else []
    parts: list[types.Part] = []
    for part in content:
        if not isinstance(part, dict):
            part = part.model_dump() if hasattr(part, "model_dump") else {}
        part_type = part.get("type")
        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                parts.append(types.Part(text=_clean_text(text)))
        elif part_type == "image_url":
            decoded = decode_data_url(_image_url_of(part))
            if decoded is None:
                # Gemini 不能直接拉取远程 URL；非 data URL 的图片只能跳过
                logger.warning("Gemini 只支持内联（data URL）图片，已跳过一张无法转换的图片")
                continue
            data, mime_type = decoded
            parts.append(types.Part(inline_data=types.Blob(data=data, mime_type=mime_type)))
    return parts


def _tool_call_fields(call: Any) -> tuple[str, str, str, Optional[bytes]]:
    """从 OpenAI 风格的 tool_call 中取出 (id, 函数名, 参数 JSON 字符串, thought_signature)"""
    if isinstance(call, dict):
        call_id = str(call.get("id") or "")
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        arguments = function.get("arguments") or "{}"
        signature = call.get(THOUGHT_SIGNATURE_KEY)
    else:  # pragma: no cover - 兜底，正常消息都是 dict
        call_id = str(getattr(call, "id", "") or "")
        function = getattr(call, "function", None)
        name = str(getattr(function, "name", "") or "")
        arguments = getattr(function, "arguments", None) or "{}"
        signature = None
    decoded_signature: Optional[bytes] = None
    if isinstance(signature, str) and signature:
        try:
            decoded_signature = base64.b64decode(signature)
        except (ValueError, binascii.Error):
            decoded_signature = None
    arguments_text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return call_id, name, _clean_text(arguments_text), decoded_signature


def _parse_arguments(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        logger.warning(f"Gemini 工具调用参数不是合法 JSON，已按空参数处理: {arguments!r}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _append_content(contents: list[types.Content], role: str, parts: list[types.Part]) -> None:
    """追加一个 Content，相邻同角色消息合并"""
    if not parts:
        return
    if contents and contents[-1].role == role:
        contents[-1].parts.extend(parts)  # type: ignore[union-attr]
        return
    contents.append(types.Content(role=role, parts=parts))


def convert_messages(messages: Messages) -> tuple[Optional[str], list[types.Content]]:
    """把消息列表转换成 ``(system_instruction, contents)``"""
    system_texts: list[str] = []
    contents: list[types.Content] = []
    tool_names: dict[str, str] = {}

    for message in messages:
        if not isinstance(message, dict):
            message = message.model_dump() if hasattr(message, "model_dump") else {}
        role = _message_role(message)
        content = _content(message)
        if role == "system":
            text = _text_of(content)
            if text:
                system_texts.append(text)
            continue
        if role == "tool":
            call_id = str(message.get("tool_call_id") or "")
            name = tool_names.get(call_id, "")
            if not name:
                # 找不到对应的 function_call（例如历史被裁剪过）：Gemini 要求函数名非空，
                # 用占位名避免整个请求直接 400
                logger.warning(f"Gemini 找不到工具调用 {call_id!r} 对应的函数名，使用占位名")
                name = "unknown_tool"
            part = types.Part(
                function_response=types.FunctionResponse(
                    id=call_id or None,
                    name=name,
                    response={"result": _text_of(content)},
                )
            )
            _append_content(contents, "user", [part])
            continue
        if role == "assistant":
            parts = content_parts(content)
            for call in message.get("tool_calls") or []:
                call_id, name, arguments, signature = _tool_call_fields(call)
                if call_id:
                    tool_names[call_id] = name
                function_call = types.FunctionCall(id=call_id or None, name=name, args=_parse_arguments(arguments))
                parts.append(types.Part(function_call=function_call, thought_signature=signature))
            _append_content(contents, "model", parts)
            continue
        # user 以及未知角色都按 user 处理
        _append_content(contents, "user", content_parts(content))

    system_instruction = "\n\n".join(system_texts) if system_texts else None
    return system_instruction, contents
