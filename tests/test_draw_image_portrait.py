"""draw_image 工具：Moonlark 画像参考图参数（moonlark_portrait）"""

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_SCHEMA = REPO_ROOT / "src" / "prompt" / "__tools__" / "draw_image.yaml"
PORTRAIT_FILE = REPO_ROOT / "src" / "plugins" / "nonebot_plugin_chat" / "resource" / "Moonlark.png"

# 生成接口返回的假图（真实 PNG，便于校验 b64 解码路径）
_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-generated-image"
_PORTRAIT_BYTES = b"\x89PNG\r\n\x1a\nfake-portrait"


def test_tool_schema_declares_optional_boolean_portrait_param() -> None:
    """moonlark_portrait 是可选的 boolean 参数，且描述说明了用途"""
    schema = yaml.safe_load(TOOL_SCHEMA.read_text(encoding="utf-8"))
    parameters = {param["name"]: param for param in schema["parameters"]}

    assert "moonlark_portrait" in parameters
    portrait = parameters["moonlark_portrait"]
    assert portrait["type"] == "boolean"
    assert portrait["required"] is False
    # 描述要告诉模型什么时候该传 true（画 Moonlark 本人时）
    assert "画像" in portrait["description"]
    assert "Moonlark" in portrait["description"]


def test_tool_schema_descriptions_have_no_braces() -> None:
    """描述文本会经过 .format() 渲染，不能包含花括号"""
    schema = yaml.safe_load(TOOL_SCHEMA.read_text(encoding="utf-8"))

    for param in schema["parameters"]:
        assert "{" not in param["description"], param["name"]
        assert "}" not in param["description"], param["name"]


def test_portrait_is_bundled_png() -> None:
    """画像已内置在插件 resource 目录中，且是 PNG 文件"""
    assert PORTRAIT_FILE.is_file()
    data = PORTRAIT_FILE.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    # 体积应远小于一兆，避免误提交超大资源
    assert len(data) < 1024 * 1024


async def test_get_moonlark_portrait_reads_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次读取磁盘，之后复用缓存"""
    from nonebot_plugin_chat.utils import portrait as mod

    monkeypatch.setattr(mod, "_portrait_cache", None)
    reads: list[str] = []

    def _fake_open(path: object, mode: str = "rb") -> Any:
        # aiofiles.open 是同步函数，返回可被 async with 使用的上下文管理器
        reads.append(str(path))
        assert "b" in mode

        class _FakeFile:
            async def read(self) -> bytes:
                return _PORTRAIT_BYTES

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc: object) -> bool:
                return False

        return _FakeFile()

    monkeypatch.setattr(mod, "aiofiles", SimpleNamespace(open=_fake_open))

    first = await mod.get_moonlark_portrait()
    second = await mod.get_moonlark_portrait()

    assert first == _PORTRAIT_BYTES
    assert second == _PORTRAIT_BYTES
    assert len(reads) == 1, "画像应被缓存，只读取一次磁盘"


class _FakeSession:
    target = "test-target"
    bot = object()


class _FakeProcessor:
    def __init__(self) -> None:
        self.session = _FakeSession()


async def _run_draw(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> tuple[dict[str, Any], str]:
    """调用 draw_image 并返回 (generate_image 收到的关键字参数, 返回值)"""
    from nonebot_plugin_chat.utils import tool_manager as tm_mod

    captured: dict[str, Any] = {}

    async def _fake_generate_image(prompt: str, **kwargs: Any) -> bytes:
        captured["prompt"] = prompt
        captured.update(kwargs)
        return _PNG_BYTES

    sent: list[bytes] = []

    class _FakeUniMessage:
        @staticmethod
        def image(raw: bytes = b"") -> "SimpleNamespace":
            async def _send(**_kwargs: object) -> None:
                sent.append(raw)

            return SimpleNamespace(send=_send)

    monkeypatch.setattr(tm_mod, "generate_image", _fake_generate_image)
    monkeypatch.setattr(tm_mod, "UniMessage", _FakeUniMessage)

    manager = tm_mod.ToolManager(processor=cast("Any", _FakeProcessor()))
    result = await manager.draw_image("画一只猫", **cast("Any", kwargs))
    assert sent == [_PNG_BYTES], "生成的图片必须发送到当前会话"
    return captured, result


async def test_draw_image_without_portrait_skips_reference_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认（不传 moonlark_portrait）不附带参考图"""
    captured, result = await _run_draw(monkeypatch)

    assert captured["reference_image"] is None
    assert result == "图片已生成并发送"
    assert captured["prompt"] == "画一只猫"


async def test_draw_image_with_portrait_passes_bundled_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """moonlark_portrait=True 时把内置画像作为参考图一并传给绘图模型"""
    from nonebot_plugin_chat.utils import tool_manager as tm_mod

    async def _fake_portrait() -> bytes:
        return _PORTRAIT_BYTES

    monkeypatch.setattr(tm_mod, "get_moonlark_portrait", _fake_portrait)

    captured, _result = await _run_draw(monkeypatch, moonlark_portrait=True)

    reference_image = captured["reference_image"]
    assert reference_image is not None
    file_name, data, mime_type = reference_image
    assert file_name == "Moonlark.png"
    assert data == _PORTRAIT_BYTES
    assert mime_type == "image/png"


@pytest.mark.parametrize("raw", ["false", "False", "FALSE", "0", "no", ""])
async def test_draw_image_coerces_falsey_string_portrait(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """模型把 false 写成字符串时不应附带参考图（非空字符串在 Python 中为真）"""
    captured, _result = await _run_draw(monkeypatch, moonlark_portrait=raw)

    assert captured["reference_image"] is None


async def test_generate_image_uses_images_edit_with_reference_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """传了参考图走 images/edit 接口，且参考图被一并提交"""
    from nonebot_plugin_openai.utils import image_generation as mod

    calls: dict[str, Any] = {}

    async def _fake_edit(**kwargs: Any) -> Any:
        calls["endpoint"] = "edit"
        calls.update(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(_PNG_BYTES).decode(), url=None)])

    class _FakeImages:
        edit = staticmethod(_fake_edit)

        async def generate(self, **_kwargs: Any) -> Any:
            raise AssertionError("传入参考图时不应调用 images.generate")

    monkeypatch.setattr(mod, "client", SimpleNamespace(images=_FakeImages()))

    async def _fake_get_model(_identify: str) -> str:
        return "gpt-image-2"

    monkeypatch.setattr(mod, "get_model_for_identify", _fake_get_model)

    result = await mod.generate_image(
        "画 Moonlark 在海边",
        reference_image=("Moonlark.png", _PORTRAIT_BYTES, "image/png"),
    )

    assert result == _PNG_BYTES
    assert calls["endpoint"] == "edit"
    assert calls["model"] == "gpt-image-2"
    assert calls["prompt"] == "画 Moonlark 在海边"
    assert calls["image"] == [("Moonlark.png", _PORTRAIT_BYTES, "image/png")]


async def test_generate_image_without_reference_image_uses_images_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不传参考图时保持原行为，走 images/generate 接口"""
    from nonebot_plugin_openai.utils import image_generation as mod

    calls: dict[str, Any] = {}

    async def _fake_generate(**kwargs: Any) -> Any:
        calls["endpoint"] = "generate"
        calls.update(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(_PNG_BYTES).decode(), url=None)])

    class _FakeImages:
        generate = staticmethod(_fake_generate)

        async def edit(self, **_kwargs: Any) -> Any:
            raise AssertionError("未传参考图时不应调用 images.edit")

    monkeypatch.setattr(mod, "client", SimpleNamespace(images=_FakeImages()))

    async def _fake_get_model(_identify: str) -> str:
        return "gpt-image-2"

    monkeypatch.setattr(mod, "get_model_for_identify", _fake_get_model)

    result = await mod.generate_image("画一只猫")

    assert result == _PNG_BYTES
    assert calls["endpoint"] == "generate"
    assert "image" not in calls


async def test_generate_image_download_url_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回 URL 时应下载图片内容"""
    from nonebot_plugin_openai.utils import image_generation as mod

    async def _fake_generate(**_kwargs: Any) -> Any:
        return SimpleNamespace(data=[SimpleNamespace(b64_json=None, url="https://example.com/a.png")])

    class _FakeResponse:
        status_code = 200
        content = _PNG_BYTES

        def raise_for_status(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

        async def get(self, _url: str) -> _FakeResponse:
            return _FakeResponse()

    monkeypatch.setattr(mod, "client", SimpleNamespace(images=SimpleNamespace(generate=_fake_generate)))

    async def _fake_get_model(_identify: str) -> str:
        return "gpt-image-2"

    monkeypatch.setattr(mod, "get_model_for_identify", _fake_get_model)
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)

    result = await mod.generate_image("画一只猫")

    assert result == _PNG_BYTES


def test_generate_image_size_validation_before_dispatch() -> None:
    """非法尺寸应在请求接口前抛出 ValueError"""
    from nonebot_plugin_openai.utils.image_generation import validate_size

    with pytest.raises(ValueError, match="16 的倍数"):
        validate_size("100x100")

    with pytest.raises(ValueError, match="不支持的图片尺寸"):
        validate_size("not-a-size")

    # 非法字符也不能绕过
    assert validate_size("auto") == "auto"
    assert validate_size("1536x864") == "1536x864"
