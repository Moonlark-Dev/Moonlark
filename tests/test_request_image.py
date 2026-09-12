"""request_image 工具：URL 图片下载、校验与上下文注入"""

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_SCHEMA = REPO_ROOT / "src" / "prompt" / "__tools__" / "request_image.yaml"


def _load_helper() -> Any:
    from nonebot_plugin_chat.utils.tools import image as mod

    return mod


def test_tool_schema_declares_url() -> None:
    """工具定义文件存在，且 url 为必填参数"""
    schema = yaml.safe_load(TOOL_SCHEMA.read_text(encoding="utf-8"))
    assert "图片" in schema["description"]
    params = {param["name"]: param for param in schema["parameters"]}
    assert params["url"]["required"] is True
    assert params["url"]["type"] == "string"


async def test_download_image_normalizes_png(monkeypatch: pytest.MonkeyPatch) -> None:
    """下载到的 PNG 应原样返回并标记为 image/png"""
    mod = _load_helper()

    async def _fake_fetch_image(_url: str) -> bytes:
        return _png_bytes()

    monkeypatch.setattr(mod, "_fetch_image", _fake_fetch_image)
    data, mime_type = await mod.download_image("https://example.com/a.png")
    assert mime_type == "image/png"
    assert data == _png_bytes()


async def test_download_image_converts_unsupported_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pillow 能读但模型不一定接受的格式（如 BMP）应转换为 JPEG"""
    mod = _load_helper()

    async def _fake_fetch_image(_url: str) -> bytes:
        return _bmp_bytes()

    monkeypatch.setattr(mod, "_fetch_image", _fake_fetch_image)
    data, mime_type = await mod.download_image("https://example.com/a.bmp")
    assert mime_type == "image/jpeg"
    assert data.startswith(b"\xff\xd8")


async def test_download_image_rejects_non_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """不是图片的内容应被拒绝，不会进入上下文"""
    mod = _load_helper()

    async def _fake_fetch_image(_url: str) -> bytes:
        return b"<html>not an image</html>"

    monkeypatch.setattr(mod, "_fetch_image", _fake_fetch_image)
    with pytest.raises(mod.ImageDownloadError):
        await mod.download_image("https://example.com/index.html")


async def test_download_image_rejects_internal_url() -> None:
    """内网地址与非 http(s) 协议应被拦截（SSRF 防护）"""
    mod = _load_helper()
    for url in ("http://127.0.0.1/a.png", "http://localhost/a.png", "file:///etc/passwd", "ftp://host/a.png"):
        with pytest.raises(mod.ImageDownloadError):
            await mod.download_image(url)


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _bmp_bytes() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 255, 0)).save(buffer, format="BMP")
    return buffer.getvalue()


class _FakeMessageQueue:
    def __init__(self) -> None:
        self.injected: list[tuple[bytes, str, str]] = []

    async def inject_image(self, image: bytes, mime_type: str, note: str) -> None:
        self.injected.append((image, mime_type, note))


class _FakeProcessor:
    def __init__(self, enable_embedded_image: bool = True) -> None:
        self.ENABLE_EMBEDDED_IMAGE = enable_embedded_image
        self.openai_messages = _FakeMessageQueue()


async def test_request_image_injects_into_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """多模态模型下，下载到的图片会被注入当前对话"""
    from nonebot_plugin_chat.utils import tool_manager as tm_mod

    processor = _FakeProcessor(enable_embedded_image=True)
    manager = tm_mod.ToolManager(processor=cast("Any", processor))

    async def _fake_download(_url: str) -> tuple[bytes, str]:
        return b"image-bytes", "image/png"

    monkeypatch.setattr(tm_mod, "download_image", _fake_download)
    result = await manager.request_image("https://example.com/a.png")

    assert processor.openai_messages.injected
    image, mime_type, note = processor.openai_messages.injected[0]
    assert (image, mime_type) == (b"image-bytes", "image/png")
    assert "example.com" in note
    assert "已加入" in result


async def test_request_image_skipped_for_text_only_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """非多模态模型下，不下载图片，直接返回提示"""
    from nonebot_plugin_chat.utils import tool_manager as tm_mod

    processor = _FakeProcessor(enable_embedded_image=False)
    manager = tm_mod.ToolManager(processor=cast("Any", processor))

    async def _fail_download(_url: str) -> tuple[bytes, str]:
        raise AssertionError("不支持图像时不应发起下载")

    monkeypatch.setattr(tm_mod, "download_image", _fail_download)
    result = await manager.request_image("https://example.com/a.png")

    assert processor.openai_messages.injected == []
    assert "不支持图像" in result
