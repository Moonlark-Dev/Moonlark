"""外部梗图源搜索从表情包搜索中拆分为独立工具的测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

QUERY = "布偶"


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """按 URL 返回预设响应的 httpx.AsyncClient 替身"""

    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> _FakeResponse:
        self.requested.append(url)
        return self.responses[url]


def _make_session(lang_str: str = "zh_hans") -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        lang_str=lang_str,
        target=None,
        bot=None,
        processor=SimpleNamespace(token_bucket=SimpleNamespace(add=lambda value: None)),
        session_id="qq_123456",
    )


async def _fake_lang_text(key: str, lang_str: str, *args, **kwargs) -> str:
    """用 zh_hans 里的真实模板渲染，避免依赖数据库中的语言包"""
    templates = {
        "sticker.search_result": "找到以下表情包：\n{}",
        "sticker.search_empty": "没有找到匹配的表情包",
        "sticker.id_not_found": "未找到 ID 为 {} 的表情包",
    }
    return templates[key].format(*args)


def _search_payload() -> dict:
    return {
        "items": [
            {
                "id": 42,
                "title": "布偶猫",
                "description": "一只布偶猫",
                "tags": ["猫", "可爱", "宠物", "多余标签"],
            }
        ]
    }


@pytest.mark.asyncio
async def test_search_meme_returns_native_positive_id() -> None:
    """meme 工具直接使用梗图源的原生正整数 ID，不再取相反数"""
    from nonebot_plugin_chat.utils.tools.meme import MemeTools

    tools = MemeTools(_make_session())
    client = _FakeAsyncClient({"https://meme-search.xxtg666.top/api/search": _FakeResponse(200, _search_payload())})

    with (
        patch("nonebot_plugin_chat.utils.tools.meme.httpx.AsyncClient", return_value=client),
        patch("nonebot_plugin_chat.utils.tools.meme.lang.text", _fake_lang_text),
    ):
        result = await tools.search_meme(QUERY)

    assert "- 42: 一只布偶猫 [猫 可爱 宠物]" in result
    assert "- -42" not in result


@pytest.mark.asyncio
async def test_search_meme_failure_returns_empty_message() -> None:
    """梗图源不可用时不抛异常，返回空结果文案"""
    from nonebot_plugin_chat.utils.tools.meme import MemeTools

    tools = MemeTools(_make_session())
    client = _FakeAsyncClient({"https://meme-search.xxtg666.top/api/search": _FakeResponse(500, {})})

    with (
        patch("nonebot_plugin_chat.utils.tools.meme.httpx.AsyncClient", return_value=client),
        patch("nonebot_plugin_chat.utils.tools.meme.lang.text", _fake_lang_text),
    ):
        result = await tools.search_meme(QUERY)

    assert result == "没有找到匹配的表情包"


@pytest.mark.asyncio
async def test_send_meme_uses_positive_id_for_metadata_and_uploads() -> None:
    """send_meme 按正整数 ID 取元数据，并从 uploads 下载图片"""
    from nonebot_plugin_chat.utils.tools.meme import MemeTools

    tools = MemeTools(_make_session())
    client = _FakeAsyncClient(
        {
            "https://meme-search.xxtg666.top/api/memes/42": _FakeResponse(200, {"filename": "ragged.jpg"}),
            "https://meme-search.xxtg666.top/uploads/ragged.jpg": _FakeResponse(200, {}),
        }
    )
    client.responses["https://meme-search.xxtg666.top/uploads/ragged.jpg"].content = b"fake-image"

    with (
        patch("nonebot_plugin_chat.utils.tools.meme.httpx.AsyncClient", return_value=client),
        patch("nonebot_plugin_chat.utils.tools.meme.UniMessage.image") as image_mock,
    ):
        image_mock.return_value.send = AsyncMock()
        result = await tools.send_meme(42)

    assert result is None
    assert client.requested == [
        "https://meme-search.xxtg666.top/api/memes/42",
        "https://meme-search.xxtg666.top/uploads/ragged.jpg",
    ]
    image_mock.assert_called_once_with(raw=b"fake-image")


@pytest.mark.asyncio
async def test_send_meme_missing_id_returns_error() -> None:
    """梗图不存在时返回错误文案，且不发送消息"""
    from nonebot_plugin_chat.utils.tools.meme import MemeTools

    tools = MemeTools(_make_session())
    client = _FakeAsyncClient({"https://meme-search.xxtg666.top/api/memes/7": _FakeResponse(404, {})})

    with (
        patch("nonebot_plugin_chat.utils.tools.meme.httpx.AsyncClient", return_value=client),
        patch("nonebot_plugin_chat.utils.tools.meme.lang.text", _fake_lang_text),
        patch("nonebot_plugin_chat.utils.tools.meme.UniMessage.image") as image_mock,
    ):
        result = await tools.send_meme(7)

    assert result == "未找到 ID 为 7 的表情包"
    image_mock.assert_not_called()


@pytest.mark.asyncio
async def test_search_sticker_no_longer_queries_external_source() -> None:
    """表情包搜索只查本地收藏，不再合并外部梗图源结果"""
    from nonebot_plugin_chat.utils.tools.sticker import StickerTools

    sticker = type("Sticker", (), {"id": 3, "description": "本地猫猫表情"})()
    tools = StickerTools(_make_session())
    tools.manager = AsyncMock()
    tools.manager.search_sticker.return_value = [sticker]

    with patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text):
        result = await tools.search_sticker(QUERY)

    assert result == "找到以下表情包：\n- 3: 本地猫猫表情"
    tools.manager.search_sticker_any.assert_not_called()


@pytest.mark.asyncio
async def test_search_sticker_empty_does_not_call_meme_source() -> None:
    """本地无结果时返回空文案，不触发梗图源请求"""
    from nonebot_plugin_chat.utils.tools.sticker import StickerTools

    tools = StickerTools(_make_session())
    tools.manager = AsyncMock()
    tools.manager.search_sticker.return_value = []
    tools.manager.search_sticker_any.return_value = []

    with (
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
        patch("nonebot_plugin_chat.utils.tools.meme.httpx.AsyncClient") as client_mock,
    ):
        result = await tools.search_sticker(QUERY)

    assert result == "没有找到匹配的表情包"
    client_mock.assert_not_called()
