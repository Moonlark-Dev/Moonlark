"""图片格式校验与归一化：模型只接受 webp/png/jpeg/gif，其余必须转换或拒绝"""

import base64
import io
from typing import Any

import pytest
from PIL import Image


def _fmt() -> Any:
    """延迟导入，确保 nonebot 插件已在会话级 fixture 中加载完毕"""
    from nonebot_plugin_chat.utils import image_format as mod

    return mod


def _make_image(pillow_format: str, mode: str = "RGB", color: Any = (255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (4, 4), color).save(buffer, format=pillow_format)
    return buffer.getvalue()


def test_supported_mime_types() -> None:
    """支持的 MIME 类型应与上游要求保持一致"""
    supported = _fmt().SUPPORTED_IMAGE_MIME_TYPES
    assert supported == {"image/webp", "image/png", "image/jpeg", "image/gif"}


@pytest.mark.parametrize(
    ("pillow_format", "mime_type", "prefix"),
    [
        ("PNG", "image/png", b"\x89PNG"),
        ("JPEG", "image/jpeg", b"\xff\xd8"),
        ("WEBP", "image/webp", b"RIFF"),
        ("GIF", "image/gif", b"GIF8"),
    ],
)
def test_normalize_keeps_supported_formats(pillow_format: str, mime_type: str, prefix: bytes) -> None:
    """受支持的格式应原样保留，并返回真实 MIME（不能一律谎报 jpeg）"""
    data = _make_image(pillow_format)
    normalized, actual_mime = _fmt().normalize_image(data)
    assert actual_mime == mime_type
    assert normalized == data
    assert normalized.startswith(prefix)


@pytest.mark.parametrize("pillow_format", ["BMP", "TIFF", "PCX"])
def test_normalize_converts_unsupported_formats(pillow_format: str) -> None:
    """Pillow 能读但模型不支持的格式应转换为 JPEG"""
    normalized, actual_mime = _fmt().normalize_image(_make_image(pillow_format))
    assert actual_mime == "image/jpeg"
    assert normalized.startswith(b"\xff\xd8")


def test_normalize_preserves_transparency_as_png() -> None:
    """带透明通道的不支持格式应转换为 PNG，避免透明区域变黑"""
    normalized, actual_mime = _fmt().normalize_image(_make_image("TIFF", mode="RGBA", color=(255, 0, 0, 0)))
    assert actual_mime == "image/png"
    assert normalized.startswith(b"\x89PNG")


def test_normalize_rejects_non_image() -> None:
    """不是图片的内容应被拒绝，不能进入模型上下文"""
    with pytest.raises(_fmt().ImageFormatError):
        _fmt().normalize_image(b"<html>not an image</html>")


def test_normalize_rejects_empty() -> None:
    """空内容应被拒绝"""
    with pytest.raises(_fmt().ImageFormatError):
        _fmt().normalize_image(b"")


def test_normalize_rejects_oversized() -> None:
    """像素数超限（解压缩炸弹）应被拒绝"""
    with pytest.raises(_fmt().ImageFormatError):
        _fmt().normalize_image(_make_image("PNG"), max_pixels=1)


def test_image_data_url_encodes_real_mime() -> None:
    """data URL 必须使用图片真实 MIME 类型"""
    data = _make_image("PNG")
    url = _fmt().image_data_url(data, "image/png")
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == data


def test_build_image_part() -> None:
    """build_image_part 返回 OpenAI 兼容的 image_url 内容块"""
    part, mime_type = _fmt().build_image_part(_make_image("PNG"))
    assert mime_type == "image/png"
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


def test_try_build_image_part_returns_none_for_invalid() -> None:
    """try_build_image_part 对非法图片返回 None 而不是抛异常"""
    assert _fmt().try_build_image_part(b"not an image") is None


def _image_part(data: bytes, mime_type: str) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(data).decode()}"}}


def test_sanitize_content_images_fixes_wrong_mime() -> None:
    """历史消息中谎报 MIME 的图片应被修正为真实类型"""
    content, removed = _fmt().sanitize_content_images([_image_part(_make_image("PNG"), "image/jpeg")])
    assert removed == 0
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_sanitize_content_images_drops_invalid_image() -> None:
    """历史消息中无法识别的图片应被移除，避免持续拖垮整轮请求"""
    invalid_part = _image_part(b"<html>", "image/jpeg")
    content, removed = _fmt().sanitize_content_images([{"type": "text", "text": "hi"}, invalid_part])
    assert removed == 1
    assert content == [{"type": "text", "text": "hi"}]


def test_sanitize_content_images_keeps_remote_url() -> None:
    """远程 URL 无法离线校验，应原样保留"""
    part = {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}}
    content, removed = _fmt().sanitize_content_images([part])
    assert removed == 0
    assert content == [part]


def test_sanitize_content_images_ignores_non_list() -> None:
    """content 不是列表时原样返回"""
    content, removed = _fmt().sanitize_content_images("plain text")
    assert (content, removed) == ("plain text", 0)


def test_sanitize_messages_images_repairs_in_place() -> None:
    """消息列表中的图片块应被就地修复，并返回移除数量"""
    messages = [
        {"role": "user", "content": [_image_part(b"<html>", "image/jpeg")]},
        {"role": "assistant", "content": "ok"},
    ]
    removed = _fmt().sanitize_messages_images(messages)
    assert removed == 1
    assert messages[0]["content"] == []
    assert messages[1]["content"] == "ok"


class _FakeOpenAIMessages:
    def __init__(self) -> None:
        self.messages: list[list[dict]] = []

    async def append_user_message(self, content: list[dict]) -> None:
        self.messages.append(content)


class _FakeProcessor:
    def __init__(self) -> None:
        self.openai_messages = _FakeOpenAIMessages()


async def test_processor_uses_real_mime_and_skips_invalid() -> None:
    """用户图片注入对话时应使用真实 MIME，非法图片被跳过而不是中断整轮请求"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    processor = _FakeProcessor()
    await MessageProcessor.append_user_message(
        processor,  # type: ignore[arg-type]
        "hello",
        [_make_image("PNG"), b"<html>not an image</html>", _make_image("BMP")],
    )

    content = processor.openai_messages.messages[0]
    urls = [part["image_url"]["url"] for part in content if part.get("type") == "image_url"]
    assert len(urls) == 2
    assert urls[0].startswith("data:image/png;base64,")
    assert urls[1].startswith("data:image/jpeg;base64,")
