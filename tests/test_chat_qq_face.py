"""QQ 官方适配器富文本表情（faceType/faceId/ext）解析测试"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

# 真实消息里的 ext 样例
# ext 中带 "+" / "/" 时上游适配器的正则匹配失败，整段标签会以纯文本形式进入解析器
FACE_EXT_WITH_PLUS = "eyJ0ZXh0Ijoi57ut5qCH6K+GIn0="  # {"text":"续标识"}
FACE_EXT_STICKER = "eyJ0ZXh0IjoiW+a7oeWktOmXruWPt10ifQ=="  # {"text":"[满头问号]"}
# 只由 [A-Za-z0-9=] 组成的 ext 会被适配器吃掉并丢掉描述文本，需要从事件原始正文里补回来
FACE_EXT_CLEAN = "eyJ0ZXh0Ijoi5L2g5aW9In0="  # {"text":"你好"}


async def _fake_lang_text(key: str, user_id: str, *args, **kwargs) -> str:
    """用 zh_hans 里的真实模板渲染，避免依赖数据库中的语言包"""
    templates = {
        "parser.emoji": "[表情: {}]",
        "parser.emoji_unknown": "[emoji:{}]",
        "parser.face_unknown": "[表情]",
    }
    return templates[key].format(*args)


def _make_parser(uni_message, raw_content: str = ""):
    from nonebot_plugin_chat.utils.message import MessageParser

    event = SimpleNamespace(content=raw_content)
    return MessageParser(uni_message, event, None, {}, "mlsid::--lang=zh_hans")


def _qq_uni_message(content: str):
    from nonebot.adapters.qq.message import Message as QQMessage
    from nonebot_plugin_alconna import UniMessage

    return UniMessage.of(QQMessage(content), adapter="QQ")


def test_decode_face_ext_from_real_samples() -> None:
    from nonebot_plugin_chat.utils.qq_face import decode_face_ext

    assert decode_face_ext(FACE_EXT_STICKER) == "满头问号"
    assert decode_face_ext(FACE_EXT_WITH_PLUS) == "续标识"
    assert decode_face_ext(FACE_EXT_CLEAN) == "你好"


def test_decode_face_ext_invalid_values() -> None:
    from nonebot_plugin_chat.utils.qq_face import decode_face_ext

    assert decode_face_ext("") is None
    assert decode_face_ext("not base64!!") is None
    # 不是 JSON 的 base64 也无法解析出描述文本
    assert decode_face_ext("aGVsbG8gd29ybGQ=") is None
    # 兜底支持未经 base64 编码的 JSON
    assert decode_face_ext('{"text": "[不看]"}') == "不看"


def test_iter_face_tags_splits_text_and_tags() -> None:
    from nonebot_plugin_chat.utils.qq_face import QQFaceTag, contains_face_tag, iter_face_tags

    text = f'a<faceType=1,faceId="4",ext="{FACE_EXT_CLEAN}">b'
    parts = list(iter_face_tags(text))
    assert parts == [
        "a",
        QQFaceTag(face_type=1, face_id="4", ext=FACE_EXT_CLEAN),
        "b",
    ]
    assert contains_face_tag(text)
    assert not contains_face_tag("普通文本")


def test_build_face_ext_map() -> None:
    from nonebot_plugin_chat.utils.qq_face import build_face_ext_map

    content = (
        f'<faceType=1,faceId="4",ext="{FACE_EXT_CLEAN}">'
        f'<faceType=4,faceId="",ext="{FACE_EXT_STICKER}">'
        f'<faceType=1,faceId="4",ext="{FACE_EXT_CLEAN}">'
    )
    # faceId 为空的标签没有可索引的 ID，重复出现的 faceId 只保留一次
    assert build_face_ext_map(content) == {"4": "你好"}
    assert build_face_ext_map("普通文本") == {}


async def test_parse_raw_face_tag_as_rich_text() -> None:
    """ext 含 +#/ 时标签会以纯文本进入解析器，应被解析成表情描述"""
    from nonebot_plugin_chat.utils import message as msg_module

    parser = _make_parser(
        _qq_uni_message(f'hi <faceType=4,faceId="",ext="{FACE_EXT_STICKER}"> end'),
        raw_content=f'hi <faceType=4,faceId="",ext="{FACE_EXT_STICKER}"> end',
    )
    with patch.object(msg_module.lang, "text", _fake_lang_text):
        assert await parser.parse() == "hi [表情: 满头问号] end"


async def test_parse_face_tag_matching_user_example() -> None:
    """用户示例：faceType=1,faceId="424",ext="eyJ0ZXh0Ijoi57ut5qCH6K+GIn0=" """
    from nonebot_plugin_chat.utils import message as msg_module

    content = f'<faceType=1,faceId="424",ext="{FACE_EXT_WITH_PLUS}">'
    parser = _make_parser(_qq_uni_message(content), raw_content=content)
    with patch.object(msg_module.lang, "text", _fake_lang_text):
        assert await parser.parse() == "[表情: 续标识]"


async def test_parse_emoji_segment_recovers_ext_from_raw_content() -> None:
    """适配器把标签转成 Emoji 段并丢掉 ext，应从事件原始正文里补回描述文本"""
    from nonebot_plugin_chat.utils import message as msg_module

    content = f'<faceType=1,faceId="4",ext="{FACE_EXT_CLEAN}">'
    uni_message = _qq_uni_message(content)
    # 该 ext 只含 [A-Za-z0-9=]，会被适配器转换成 Emoji 段
    assert [type(seg).__name__ for seg in uni_message] == ["Emoji"]

    parser = _make_parser(uni_message, raw_content=content)
    with patch.object(msg_module.lang, "text", _fake_lang_text):
        assert await parser.parse() == "[表情: 你好]"


async def test_parse_face_without_ext_falls_back_to_emoji_map() -> None:
    from nonebot_plugin_chat.utils import message as msg_module

    parser = _make_parser(_qq_uni_message(""))
    with patch.object(msg_module.lang, "text", _fake_lang_text):
        # 已知的 QQ 系统表情按内置映射表输出名称
        assert await parser.parse_face("4") == "[表情: 得意]"
        # 未知 ID 保留原始 ID，缺少 ID 时输出占位文本
        assert await parser.parse_face("99999") == "[emoji:99999]"
        assert await parser.parse_face("") == "[表情]"
        assert await parser.parse_face("0") == "[表情]"


async def test_parse_other_face_segment() -> None:
    """原生 face / emoji 段未映射成 uniseg 段时同样应被识别"""
    from nonebot_plugin_chat.utils import message as msg_module

    parser = _make_parser(_qq_uni_message(""))
    with patch.object(msg_module.lang, "text", _fake_lang_text):
        segment = SimpleNamespace(type="face", data={"id": "4"})
        assert await parser.parse_special_segment(segment) == "[表情: 得意]"
        segment = SimpleNamespace(type="emoji", data={"id": "99999"})
        assert await parser.parse_special_segment(segment) == "[emoji:99999]"
