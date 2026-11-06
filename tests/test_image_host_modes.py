"""nonebot_plugin_larkutils markdown 消息图床双模式回归测试。

对象存储模式沿用 R2_* 配置直传 S3 兼容存储；自建图床模式把图片写进本地目录，
由 nonebot 的 FastAPI app 提供访问，对外基础 URL 独立于 MOONLARK_API_BASE。
"""

import os
import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image


def _png(width: int = 120, height: int = 80) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (12, 34, 56)).save(buffer, format="PNG")
    return buffer.getvalue()


def _get_config():
    from nonebot_plugin_larkutils.config import config

    return config


def _get_host():
    from nonebot_plugin_larkutils.image_host import host

    return host


def _use_self_hosted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, base_url: str = "https://img.example.com"
) -> None:
    from nonebot_plugin_larkutils.image_host import self_hosted

    config = _get_config()
    monkeypatch.setattr(config, "image_host_mode", "self_hosted")
    monkeypatch.setattr(config, "image_host_base_url", base_url)
    monkeypatch.setattr(config, "image_host_route", "/image-host")
    monkeypatch.setattr(config, "image_host_object_ttl", 604800)
    monkeypatch.setattr(self_hosted, "_get_storage_dir", lambda: tmp_path)
    # 自建图床不应触碰对象存储配置
    monkeypatch.setattr(config, "r2_access_key_id", "")
    monkeypatch.setattr(config, "r2_secret_access_key", "")
    monkeypatch.setattr(config, "r2_bucket_name", "")
    monkeypatch.setattr(config, "r2_public_base_url", "")
    monkeypatch.setattr(config, "r2_account_id", "")
    monkeypatch.setattr(config, "r2_endpoint_url", "")


async def test_object_storage_mode_dispatches_to_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _get_host()
    config = _get_config()
    monkeypatch.setattr(config, "image_host_mode", "object_storage")
    seen: dict[str, object] = {}

    async def fake_upload(data: bytes, image_id: str | None = None, ext: str | None = None) -> str:
        seen.update({"data": data, "image_id": image_id, "ext": ext})
        return "https://pub.example.com/abc123.png"

    monkeypatch.setattr(host.object_storage, "upload_image", fake_upload)
    data = _png(120, 80)

    code = await host.create_image_markdown(data, image_id="abc123", ext="png")

    assert code == "![text #120px #80px](https://pub.example.com/abc123.png)"
    assert seen == {"data": data, "image_id": "abc123", "ext": "png"}


async def test_self_hosted_mode_writes_local_file_without_r2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    host = _get_host()
    _use_self_hosted(monkeypatch, tmp_path)

    async def unexpected_upload(*_: object, **__: object) -> str:
        raise AssertionError("自建图床模式不应调用对象存储上传")

    monkeypatch.setattr(host.object_storage, "upload_image", unexpected_upload)
    data = _png(120, 80)

    code = await host.create_image_markdown(data, image_id="abc123", ext="png")

    assert code == "![text #120px #80px](https://img.example.com/image-host/abc123.png)"
    assert (tmp_path / "abc123.png").read_bytes() == data


async def test_self_hosted_mode_uses_independent_base_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    host = _get_host()
    _use_self_hosted(monkeypatch, tmp_path, base_url="https://cdn.example.com/bed/")

    code = await host.create_image_markdown(_png(), image_id="independent", ext="png")

    assert code.endswith("](https://cdn.example.com/bed/image-host/independent.png)")


async def test_self_hosted_mode_requires_base_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    host = _get_host()
    _use_self_hosted(monkeypatch, tmp_path, base_url="")

    with pytest.raises(RuntimeError, match="IMAGE_HOST_BASE_URL"):
        await host.create_image_markdown(_png())

    # 配置缺失时不应留下无法引用的文件
    assert list(tmp_path.iterdir()) == []


async def test_self_hosted_mode_rejects_unsafe_image_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    host = _get_host()
    _use_self_hosted(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        await host.create_image_markdown(_png(), image_id="../../etc/passwd", ext="png")


async def test_self_hosted_serve_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from nonebot_plugin_larkutils.image_host import self_hosted

    _use_self_hosted(monkeypatch, tmp_path)
    (tmp_path / "abc123.png").write_bytes(_png())

    response = await self_hosted.serve_image("abc123.png")

    assert response.path == tmp_path / "abc123.png"
    assert response.media_type == "image/png"
    assert response.headers["cache-control"] == "public, max-age=86400"

    with pytest.raises(HTTPException) as unsafe:
        await self_hosted.serve_image("..%2Fetc%2Fpasswd")
    assert unsafe.value.status_code == 404

    with pytest.raises(HTTPException) as missing:
        await self_hosted.serve_image("missing.png")
    assert missing.value.status_code == 404


def test_register_image_route(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nonebot_plugin_larkutils.image_host import self_hosted

    _use_self_hosted(monkeypatch, tmp_path)
    app = FastAPI()
    monkeypatch.setattr(self_hosted, "_registered", False)
    monkeypatch.setattr(self_hosted, "get_app", lambda: app)

    self_hosted.register_image_route()

    assert any(getattr(route, "path", None) == "/image-host/{filename}" for route in app.routes)
    assert self_hosted._registered is True

    # 重复调用不应重复挂载
    self_hosted.register_image_route()
    assert sum(1 for route in app.routes if getattr(route, "path", None) == "/image-host/{filename}") == 1

    # 路由确实能返回图床目录里的图片
    data = _png()
    (tmp_path / "abc123.png").write_bytes(data)
    client = TestClient(app)
    response = client.get("/image-host/abc123.png")
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert client.get("/image-host/missing.png").status_code == 404


async def test_self_hosted_cleanup_expired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from nonebot_plugin_larkutils.config import config
    from nonebot_plugin_larkutils.image_host import self_hosted

    _use_self_hosted(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "image_host_object_ttl", 3600)
    old = tmp_path / "old.png"
    fresh = tmp_path / "fresh.png"
    old.write_bytes(_png())
    fresh.write_bytes(_png())
    stale_time = time.time() - 7200
    os.utime(old, (stale_time, stale_time))

    removed = await self_hosted._cleanup_expired()

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


async def test_self_hosted_cleanup_can_be_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from nonebot_plugin_larkutils.config import config
    from nonebot_plugin_larkutils.image_host import self_hosted

    _use_self_hosted(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "image_host_object_ttl", 0)
    old = tmp_path / "old.png"
    old.write_bytes(_png())
    stale_time = time.time() - 7200
    os.utime(old, (stale_time, stale_time))

    assert await self_hosted._cleanup_expired() == 0
    assert old.exists()


def test_config_normalizes_image_host_values() -> None:
    from nonebot_plugin_larkutils.config import Config

    defaults = Config(
        baidu_api_key="",
        baidu_secret_key="",
        superusers=set(),
        command_start=["/"],
        image_host_mode="",
        image_host_route="",
        image_host_object_ttl="",
    )
    assert defaults.image_host_mode == "object_storage"
    assert defaults.image_host_route == "/image-host"
    assert defaults.image_host_object_ttl == 604800

    normalized = Config(
        baidu_api_key="",
        baidu_secret_key="",
        superusers=set(),
        command_start=["/"],
        image_host_mode="self_hosted",
        image_host_route="img/",
        image_host_object_ttl=60,
    )
    assert normalized.image_host_mode == "self_hosted"
    assert normalized.image_host_route == "/img"
    assert normalized.image_host_object_ttl == 60
