"""自建图床模式：图片写入本地磁盘，由 nonebot 的 FastAPI app 提供访问

该模式不需要任何 R2_* 配置，对外基础 URL 通过 IMAGE_HOST_BASE_URL 独立配置，
与 MOONLARK_API_BASE 无关。
"""

import asyncio
import mimetypes
import re
import time
from pathlib import Path

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from nonebot import get_app, get_driver, logger
from nonebot.drivers import ASGIMixin
from nonebot_plugin_localstore import get_cache_dir

from ..config import config
from .common import build_image_name

PLUGIN_NAME = "nonebot_plugin_larkutils"
IMAGE_CACHE_SUBDIR = "image_host"
# 文件名由 build_image_name 生成，限制字符集以避免路径穿越
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}\.[A-Za-z0-9]{2,8}$")
_CACHE_CONTROL = "public, max-age=86400"
# 清理过期图片的最小间隔（秒），避免每次上传都扫描目录
_CLEANUP_INTERVAL = 3600.0

_registered = False
_last_cleanup = 0.0
_cleanup_lock = asyncio.Lock()


def _get_storage_dir() -> Path:
    if config.image_host_storage_dir:
        return Path(config.image_host_storage_dir).expanduser()
    return get_cache_dir(PLUGIN_NAME) / IMAGE_CACHE_SUBDIR


def _get_route_path() -> str:
    return config.image_host_route


def get_base_url() -> str:
    """自建图床对外基础 URL；独立于 MOONLARK_API_BASE 配置"""
    base_url = config.image_host_base_url.strip().rstrip("/")
    if not base_url:
        raise RuntimeError(
            "自建图床未配置 IMAGE_HOST_BASE_URL：请填写图片对外可访问的基础 URL（独立于 MOONLARK_API_BASE），"
            "例如 https://bot.example.com",
        )
    return base_url


def get_public_url(filename: str) -> str:
    return f"{get_base_url()}{_get_route_path()}/{filename}"


def _write_atomic(path: Path, data: bytes) -> None:
    # 先写临时文件再原子替换，避免访问到只写了一半的图片
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(data)
    temp_path.replace(path)


def _list_files(directory: Path) -> list[Path]:
    try:
        return [path for path in directory.iterdir() if path.is_file()]
    except FileNotFoundError:
        return []


async def upload_image(data: bytes, image_id: str | None = None, ext: str | None = None) -> str:
    """把原图写入本地图床目录，返回图片可访问 URL（不做压缩）

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据图片内容推断
    """
    filename, _ = build_image_name(data, image_id, ext)
    if not _FILENAME_PATTERN.fullmatch(filename):
        raise ValueError(f"非法的图床文件名: {filename}")
    # 先校验公网地址配置，避免写入随后无法引用的文件
    public_url = get_public_url(filename)
    directory = _get_storage_dir()
    directory.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_write_atomic, directory / filename, data)
    await _maybe_cleanup_expired()
    return public_url


async def serve_image(filename: str) -> FileResponse:
    """FastAPI 路由：返回图床中的图片文件"""
    if not _FILENAME_PATTERN.fullmatch(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    path = _get_storage_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        headers={"Cache-Control": _CACHE_CONTROL},
    )


def register_image_route() -> None:
    """把图床路由挂到 nonebot 的 FastAPI app 上（仅 self_hosted 模式调用）"""
    global _registered
    if _registered:
        return
    if not isinstance(get_driver(), ASGIMixin):
        logger.warning("自建图床需要 ASGI 驱动（如 ~fastapi），当前驱动不支持，已跳过图床路由注册")
        return
    if not config.image_host_base_url.strip():
        logger.warning("自建图床未配置 IMAGE_HOST_BASE_URL，发送 markdown 图片时将失败")
    route = f"{_get_route_path()}/{{filename}}"
    get_app().add_api_route(route, serve_image, methods=["GET"], name="larkutils_image_host")
    _registered = True
    logger.info(f"自建图床已挂载：{route}")


async def _cleanup_expired() -> int:
    """删除超过 IMAGE_HOST_OBJECT_TTL 的图片，返回删除数量"""
    if config.image_host_object_ttl <= 0:
        return 0
    directory = _get_storage_dir()
    cutoff = time.time() - config.image_host_object_ttl
    removed = 0
    for path in await asyncio.to_thread(_list_files, directory):
        try:
            if (await asyncio.to_thread(path.stat)).st_mtime >= cutoff:
                continue
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            continue
        removed += 1
    return removed


async def _maybe_cleanup_expired() -> None:
    global _last_cleanup
    if time.monotonic() - _last_cleanup < _CLEANUP_INTERVAL:
        return
    async with _cleanup_lock:
        if time.monotonic() - _last_cleanup < _CLEANUP_INTERVAL:
            return
        _last_cleanup = time.monotonic()
        try:
            if removed := await _cleanup_expired():
                logger.info(f"自建图床已清理 {removed} 个过期图片")
        except Exception as e:
            logger.exception(f"自建图床清理过期图片失败: {e}")
