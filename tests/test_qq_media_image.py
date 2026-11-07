"""nonebot_plugin_larkutils markdown 图片（QQ 素材管理）回归测试。

图片不再经过外部图床，而是走 QQ 官方机器人的
``/v2/media-images`` prepare → PUT → complete 流程换成 ``qqbot-media://`` 引用；
数量超限（40035007）时清理最早上传的图片后重试。
"""

import hashlib
import json
import time
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.drivers import Response
from PIL import Image


def _png(width: int = 120, height: int = 80, color: tuple[int, int, int] = (12, 34, 56)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _bot(appid: str = "102000001") -> SimpleNamespace:
    return SimpleNamespace(self_id=appid)


def _prepare_response(upload_id: str = "upload_1") -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "presigned_url": f"https://upload.example.com/{upload_id}",
        "expires_in": 3600,
    }


def _complete_response(image_id: str = "img_1", url: str = "qqbot-media://image/v1/token") -> dict[str, Any]:
    return {"image_id": image_id, "url": url, "ttl": 7776000, "preview_url": "https://preview.example.com/x"}


@pytest.fixture(autouse=True)
def _clear_media_cache() -> Any:
    from nonebot_plugin_larkutils import media_image

    media_image._CACHE.clear()  # ruff: ignore[private-member-access]
    yield
    media_image._CACHE.clear()  # ruff: ignore[private-member-access]


def _install_media_api(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[tuple[str, tuple[str, ...], dict[str, Any]]],
    puts: list[Any],
) -> None:
    from nonebot_plugin_larkutils import media_image

    async def fake_api(bot: Any, method: str, *segments: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, segments, kwargs))
        if segments[-1] == "prepare":
            return _prepare_response()
        if segments[-1] == "complete":
            return _complete_response()
        raise AssertionError(f"未预期的素材接口调用：{method} {segments}")

    async def fake_put(bot: Any, url: str, payload: Any) -> None:
        puts.append((url, payload))

    monkeypatch.setattr(media_image, "_api_request", fake_api)
    monkeypatch.setattr(media_image, "_put_presigned", fake_put)


async def test_create_image_markdown_upload_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """上传走 prepare → PUT → complete，返回带尺寸的 qqbot-media 引用"""
    from nonebot_plugin_larkutils import media_image

    calls: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
    puts: list[Any] = []
    _install_media_api(monkeypatch, calls, puts)
    data = _png(120, 80)

    code = await media_image.create_image_markdown(data, _bot())

    assert code == "![text #120px #80px](qqbot-media://image/v1/token)"
    assert [call[0] for call in calls] == ["POST", "POST"]
    assert calls[0][1] == ("media-images", "prepare")
    assert calls[1][1] == ("media-images", "complete")

    prepare = calls[0][2]["json"]
    assert prepare["file_size"] == len(data)
    assert prepare["content_type"] == "image/png"
    assert prepare["file_name"].endswith(".png")
    assert prepare["md5"] == hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert prepare["sha1"] == hashlib.sha1(data, usedforsecurity=False).hexdigest()
    assert calls[1][2]["json"]["md5"] == prepare["md5"]

    assert len(puts) == 1
    assert puts[0][0] == "https://upload.example.com/upload_1"
    assert puts[0][1].data == data
    assert puts[0][1].content_type == "image/png"


async def test_same_image_is_uploaded_once_per_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    """相同图片在同一机器人上复用引用；不同机器人的引用不互通"""
    from nonebot_plugin_larkutils import media_image

    calls: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
    puts: list[Any] = []
    _install_media_api(monkeypatch, calls, puts)
    data = _png()
    bot = _bot("app-a")

    await media_image.create_image_markdown(data, bot)
    await media_image.create_image_markdown(data, bot)
    assert sum(1 for call in calls if call[1][-1] == "prepare") == 1

    await media_image.create_image_markdown(data, _bot("app-b"))
    assert sum(1 for call in calls if call[1][-1] == "prepare") == 2


async def test_quota_exceeded_cleans_up_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """数量超限（40035007）时清理旧图片并重试一次"""
    from nonebot_plugin_larkutils import media_image

    cleaned: list[Any] = []
    attempts: list[str] = []

    async def fake_upload_once(bot: Any, payload: Any, digest: str) -> tuple[str, str]:
        attempts.append(digest)
        if len(attempts) == 1:
            raise ActionFailed(Response(400, content=json.dumps({"code": 40035007, "message": "too many images"})))
        return "qqbot-media://image/v1/retry", "img_retry"

    async def fake_cleanup(bot: Any, count: int = media_image.CLEANUP_BATCH) -> int:
        cleaned.append(bot)
        return count

    monkeypatch.setattr(media_image, "_upload_once", fake_upload_once)
    monkeypatch.setattr(media_image, "delete_oldest_images", fake_cleanup)
    bot = _bot()

    code = await media_image.create_image_markdown(_png(120, 80), bot)

    assert code == "![text #120px #80px](qqbot-media://image/v1/retry)"
    assert len(attempts) == 2
    assert cleaned == [bot]


async def test_quota_error_still_skips_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """非配额错误不应触发清理"""
    from nonebot_plugin_larkutils import media_image

    async def fake_upload_once(bot: Any, payload: Any, digest: str) -> tuple[str, str]:
        raise ActionFailed(Response(500, content=json.dumps({"code": 40035006, "message": "server error"})))

    async def unexpected_cleanup(bot: Any, count: int = media_image.CLEANUP_BATCH) -> int:
        raise AssertionError("非配额错误不应清理图片")

    monkeypatch.setattr(media_image, "_upload_once", fake_upload_once)
    monkeypatch.setattr(media_image, "delete_oldest_images", unexpected_cleanup)

    with pytest.raises(ActionFailed):
        await media_image.create_image_markdown(_png(), _bot())


async def test_delete_oldest_images_keeps_recent_and_invalidates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理优先删除超过宽限期的旧图片，并同时移除对应的引用缓存"""
    from nonebot_plugin_larkutils import media_image

    now = int(time.time())
    images = [
        {"image_id": "fresh", "created_at": now - 10},
        {"image_id": "old_1", "created_at": now - 7200},
        {"image_id": "old_2", "created_at": now - 3600},
    ]
    deleted: list[str] = []

    async def fake_api(bot: Any, method: str, *segments: str, **kwargs: Any) -> dict[str, Any]:
        if method == "GET":
            return {"images": images, "next_cursor": "", "total": len(images)}
        if method == "DELETE":
            deleted.append(segments[1])
            return {}
        raise AssertionError(f"未预期的素材接口调用：{method} {segments}")

    bot = _bot("app-old")
    media_image._CACHE["app-old", "md5-old"] = media_image._CachedImage("old_2", "qqbot-media://image/v1/old")
    media_image._CACHE["app-old", "md5-fresh"] = media_image._CachedImage("fresh", "qqbot-media://image/v1/fresh")
    monkeypatch.setattr(media_image, "_api_request", fake_api)

    removed = await media_image.delete_oldest_images(bot, count=2)

    assert removed == 2
    assert deleted == ["old_1", "old_2"]
    assert ("app-old", "md5-old") not in media_image._CACHE
    assert ("app-old", "md5-fresh") in media_image._CACHE


async def test_list_images_follows_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """图片列表接口按 next_cursor 翻页"""
    from nonebot_plugin_larkutils import media_image

    pages = [
        {"images": [{"image_id": "a"}], "next_cursor": "c2", "total": 2},
        {"images": [{"image_id": "b"}], "next_cursor": "", "total": 2},
    ]
    seen: list[Any] = []

    async def fake_api(bot: Any, method: str, *segments: str, **kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs.get("params"))
        return pages[len(seen) - 1]

    monkeypatch.setattr(media_image, "_api_request", fake_api)

    images = await media_image.list_images(_bot())

    assert [image["image_id"] for image in images] == ["a", "b"]
    assert seen == [None, {"cursor": "c2"}]


def test_normalize_converts_bmp_to_png() -> None:
    """素材接口不支持 bmp，上传前转成 PNG"""
    from nonebot_plugin_larkutils import media_image

    buffer = BytesIO()
    Image.new("RGB", (10, 10), (1, 2, 3)).save(buffer, format="BMP")

    payload = media_image.normalize_image(buffer.getvalue())

    assert payload.content_type == "image/png"
    assert payload.ext == "png"
    assert payload.data.startswith(b"\x89PNG\r\n\x1a\n")


def test_normalize_compresses_oversized_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """超过大小上限的图片重新编码到限制以内"""
    from nonebot_plugin_larkutils import media_image

    monkeypatch.setattr(media_image, "MAX_IMAGE_BYTES", 3000)
    buffer = BytesIO()
    image = Image.effect_noise((160, 160), 100).convert("RGB")
    image.save(buffer, format="PNG")

    payload = media_image.normalize_image(buffer.getvalue())

    assert len(payload.data) <= 3000
    assert payload.content_type == "image/jpeg"
    assert media_image.detect_image_size(payload.data) != (media_image.DEFAULT_WIDTH, media_image.DEFAULT_HEIGHT)


async def test_invalid_image_data_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """无法识别的内容直接报错，不发起任何上传请求"""
    from nonebot_plugin_larkutils import media_image

    async def unexpected_api(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("无效图片不应调用素材接口")

    monkeypatch.setattr(media_image, "_api_request", unexpected_api)

    with pytest.raises(ValueError, match="无法识别"):
        await media_image.create_image_markdown(b"definitely not an image", _bot())
