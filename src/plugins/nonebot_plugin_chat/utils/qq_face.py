"""QQ 官方适配器富文本表情（``faceType`` / ``faceId`` / ``ext``）解析。

QQ 官方接口会把聊天中的表情以标签形式塞进消息正文，例如::

    <faceType=1,faceId="424",ext="eyJ0ZXh0Ijoi57ut5qCH6K+GIn0=">

其中 ``faceType`` 表示表情类型（1 为系统表情，4 为表情包/超大表情等），``faceId``
是系统表情 ID（表情包消息可能为空字符串），``ext`` 是 base64 编码的 JSON，通常形如
``{"text": "[满头问号]"}``，携带表情的文本描述。

上游适配器的正则只接受数字 ``faceId`` 与由 ``[\\w=]`` 组成的 ``ext``，因此
``faceId=""`` 或 ext 中出现 ``+`` / ``/`` / ``-`` 时会整段标签原样留在文本里，被当作
纯文本交给模型；即使匹配成功也只保留 faceId 而丢掉 ext 里的描述文本。本模块负责把这些
标签还原成可读文本。
"""

import base64
import binascii
import json
import re
from typing import Iterator, NamedTuple, Optional, Union

# 匹配 <faceType=1,faceId="424",ext="..."> 形式的富文本表情标签
FACE_TAG_PATTERN = re.compile(
    r"<faceType=(?P<face_type>\d+)" r',faceId="(?P<face_id>[^"]*)"' r'(?:,ext="(?P<ext>[^"]*)")?' r"\s*/?>"
)

# 标记一个会话表情是否为空（faceId="0" 或空字符串都表示没有系统表情 ID）
_EMPTY_FACE_IDS = {"", "0"}


class QQFaceTag(NamedTuple):
    """一段 QQ 富文本表情标签"""

    face_type: int
    face_id: str
    ext: str


def _decode_base64(value: str) -> Optional[bytes]:
    """解码 base64 字符串，兼容 URL-safe 字母表并自动补齐 padding"""
    data = value.strip().replace("-", "+").replace("_", "/")
    data += "=" * (-len(data) % 4)
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _extract_text(payload: object) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        # ext 中的描述通常自带方括号（如 "[满头问号]"），去掉外层括号避免出现 [[...]]
        return text.strip().strip("[]").strip() or None
    return None


def decode_face_ext(ext: str) -> Optional[str]:
    """解码 ``ext`` 字段并返回其中的表情描述文本，无法解析时返回 None"""
    if not ext:
        return None
    raw = _decode_base64(ext)
    if raw is not None:
        try:
            text = _extract_text(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            text = None
        if text:
            return text
    # 少数实现直接给出 JSON 而不是 base64，这里做一次兜底
    try:
        return _extract_text(json.loads(ext))
    except json.JSONDecodeError:
        return None


def iter_face_tags(text: str) -> Iterator[Union[str, QQFaceTag]]:
    """把文本按富文本表情标签拆开，依次产出纯文本与 :class:`QQFaceTag`"""
    position = 0
    for match in FACE_TAG_PATTERN.finditer(text):
        if match.start() > position:
            yield text[position : match.start()]
        yield QQFaceTag(
            face_type=int(match.group("face_type")),
            face_id=match.group("face_id") or "",
            ext=match.group("ext") or "",
        )
        position = match.end()
    if position < len(text):
        yield text[position:]


def contains_face_tag(text: str) -> bool:
    """判断文本中是否含有富文本表情标签"""
    return FACE_TAG_PATTERN.search(text) is not None


def build_face_ext_map(content: str) -> dict[str, str]:
    """从原始消息文本中提取 ``faceId -> 表情描述`` 的映射

    上游适配器把标签转换成 Emoji 段时会丢掉 ``ext``，只能从事件原始文本里把描述补回来。
    同一个 faceId 的描述文本是固定的，因此这里可以直接按 faceId 索引。
    """
    mapping: dict[str, str] = {}
    for part in iter_face_tags(content):
        if not isinstance(part, QQFaceTag) or not part.face_id:
            continue
        if text := decode_face_ext(part.ext):
            mapping.setdefault(part.face_id, text)
    return mapping


def is_empty_face_id(face_id: str) -> bool:
    """判断 faceId 是否表示「没有系统表情 ID」"""
    return face_id.strip() in _EMPTY_FACE_IDS
