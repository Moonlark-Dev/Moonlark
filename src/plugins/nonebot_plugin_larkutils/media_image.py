"""QQ 官方机器人 Markdown 图片：通过「素材管理」接口上传并返回平台内引用

QQ 官方机器人允许把 Markdown 消息所需的图片预先上传到平台，拿到 ``qqbot-media://``
引用后写进 Markdown，无需任何外部图床。实现遵循官方文档的四个接口：

1. ``POST /v2/media-images/prepare`` 申请上传，拿到预签名 URL；
2. ``PUT <presigned_url>`` 直传图片二进制；
3. ``POST /v2/media-images/complete`` 换取 ``image_id`` 与引用链接；
4. 配额用满时用 ``GET /v2/media-images`` 与
   ``DELETE /v2/media-images/{image_id}/delete`` 清理最早上传的图片。

文档：https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/material-management.html

平台限制：单张不超过 10MB、只接受 png/jpeg/gif/webp、单机器人最多保存 100 张、
图片自最后一次被消息引用起 90 天滑动过期。上传前会把平台不支持的格式转成 PNG，
把超过 10MB 的图片压到限制以内；prepare/complete 返回 40035007（数量超限）时
删除最早上传的一批图片后重试。
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Any

from nonebot import logger
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.drivers import Request
from PIL import Image

if TYPE_CHECKING:
    from nonebot.adapters.qq import Bot as QQBot

# 单张图片大小上限（平台默认 10MB）
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# 单机器人可保存的图片数量上限
MAX_IMAGE_COUNT = 100
# 配额用满时一次清理的图片数量，清理后留出余量避免每次上传都触发清理
CLEANUP_BATCH = 20
# 清理时优先保留刚上传的图片，避免删除正在被消息引用的图片
CLEANUP_GRACE_SECONDS = 300
# 平台返回的图片数量超限错误码
QUOTA_EXCEEDED_CODE = 40035007

DEFAULT_WIDTH = 208
DEFAULT_HEIGHT = 320


@dataclass(frozen=True, slots=True)
class _CachedImage:
    image_id: str
    url: str


@dataclass(frozen=True, slots=True)
class _ImagePayload:
    data: bytes
    content_type: str
    ext: str


# 同一张图片只需上传一次；按 (bot.self_id, md5) 缓存，因为 qqbot-media 引用与机器人绑定
_CACHE: OrderedDict[tuple[str, str], _CachedImage] = OrderedDict()
_CACHE_MAX = 256


def _sniff_image_type(data: bytes) -> tuple[str, str] | None:
    """根据文件头判断素材接口支持的图片类型，无法识别时返回 ``None``"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    return None


def detect_image_size(data: bytes) -> tuple[int, int]:
    """读取图片尺寸，解析失败时回退到默认尺寸"""
    try:
        with Image.open(BytesIO(data)) as image:
            return image.size
    except Exception:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT


def _compress_to_limit(image: Image.Image) -> bytes:
    """把图片重新编码为 JPEG，压到素材接口的大小上限以内"""
    frame = image.convert("RGB") if image.mode not in ("RGB", "L") else image
    for quality in (90, 75, 60, 45):
        buffer = BytesIO()
        frame.save(buffer, format="JPEG", quality=quality, optimize=True)
        if buffer.tell() <= MAX_IMAGE_BYTES:
            return buffer.getvalue()
    while min(frame.size) > 16:
        frame = frame.resize(
            (max(1, frame.width * 3 // 4), max(1, frame.height * 3 // 4)),
            Image.Resampling.LANCZOS,
        )
        buffer = BytesIO()
        frame.save(buffer, format="JPEG", quality=70, optimize=True)
        if buffer.tell() <= MAX_IMAGE_BYTES:
            return buffer.getvalue()
    raise ValueError(f"图片压缩后仍超过 {MAX_IMAGE_BYTES} 字节上限")


def normalize_image(data: bytes) -> _ImagePayload:
    """把图片转换成素材接口接受的格式与大小

    - png/jpeg/gif/webp 且未超过 10MB：原样上传（不做压缩）；
    - bmp 等不支持的格式：转成 PNG；
    - 超过 10MB：重新编码为 JPEG（必要时缩放），直到满足限制。
    """
    image_type = _sniff_image_type(data)
    if image_type is not None and len(data) <= MAX_IMAGE_BYTES:
        content_type, ext = image_type
        return _ImagePayload(data=data, content_type=content_type, ext=ext)

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image_type is None:
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                return _ImagePayload(data=buffer.getvalue(), content_type="image/png", ext="png")
            return _ImagePayload(data=_compress_to_limit(image), content_type="image/jpeg", ext="jpg")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("无法识别的图片数据，仅支持 png/jpeg/gif/webp（其它格式会尝试转换为 PNG）") from e


def build_image_markdown(url: str, data: bytes) -> str:
    """生成 QQ 适配器可用的 markdown 图片代码（带渲染尺寸）"""
    width, height = detect_image_size(data)
    return f"![text #{width}px #{height}px]({url})"


async def _api_request(bot: QQBot, method: str, *segments: str, **kwargs: Any) -> dict[str, Any]:
    """调用 QQ 开放平台接口并返回解析后的 JSON"""
    request = Request(method, bot.adapter.get_api_base().joinpath("v2", *segments), **kwargs)
    # 适配器尚未封装素材管理接口，复用其带鉴权与 access_token 刷新的通用请求方法
    data = await bot._request(request)  # ruff: ignore[private-member-access]
    return data if isinstance(data, dict) else {}


async def _put_presigned(bot: QQBot, url: str, payload: _ImagePayload) -> str | None:
    """把图片二进制直传到预签名 URL（该请求不能携带 Authorization 头）

    返回 COS 响应中的 ETag（去掉引号），也就是单次 PUT 写入对象的 MD5；
    没有返回 ETag 时由调用方回退到本地计算的 MD5。
    """
    response = await bot.adapter.request(
        Request(
            "PUT",
            url,
            content=payload.data,
            headers={"Content-Type": payload.content_type},
            timeout=60,
        ),
    )
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"上传图片到 QQ 素材库失败（HTTP {response.status_code}）")
    etag = response.headers.get("ETag") or response.headers.get("etag")
    if not etag:
        return None
    return etag.strip().removeprefix("W/").strip('"')


async def _upload_once(bot: QQBot, payload: _ImagePayload, digest: str) -> tuple[str, str]:
    """执行一次 prepare → PUT → complete，返回 (引用链接, image_id)"""
    prepare = await _api_request(
        bot,
        "POST",
        "media-images",
        "prepare",
        json={
            "file_name": f"{digest}.{payload.ext}",
            "file_size": len(payload.data),
            "content_type": payload.content_type,
            "md5": digest,
            "sha1": hashlib.sha1(payload.data, usedforsecurity=False).hexdigest(),
        },
    )
    upload_id = str(prepare["upload_id"])
    # complete 需要与对象实际 ETag 一致；单次 PUT 的 ETag 就是文件 MD5
    uploaded_md5 = await _put_presigned(bot, str(prepare["presigned_url"]), payload) or digest
    complete = await _api_request(
        bot,
        "POST",
        "media-images",
        "complete",
        json={"upload_id": upload_id, "md5": uploaded_md5},
    )
    return str(complete["url"]), str(complete["image_id"])


async def list_images(bot: QQBot) -> list[dict[str, Any]]:
    """列出当前机器人仍有效的图片（按上传时间倒序）"""
    images: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params = {"cursor": cursor} if cursor else None
        data = await _api_request(bot, "GET", "media-images", params=params)
        images.extend(image for image in data.get("images") or [] if isinstance(image, dict))
        cursor = data.get("next_cursor") or None
        if not cursor or len(images) >= MAX_IMAGE_COUNT * 2:
            break
    return images


def _forget_cached_image(bot_id: str, image_id: str) -> None:
    for key, cached in list(_CACHE.items()):
        if key[0] == bot_id and cached.image_id == image_id:
            del _CACHE[key]


async def delete_oldest_images(bot: QQBot, count: int = CLEANUP_BATCH) -> int:
    """删除最早上传的 ``count`` 张图片以释放配额，返回实际删除数量

    刚上传的图片会被消息立即引用，因此优先删除上传超过 ``CLEANUP_GRACE_SECONDS``
    的图片；若没有可删除的旧图片，则退而删除最早上传的图片，避免配额彻底用满。
    """
    images = await list_images(bot)
    if not images:
        return 0
    now = time.time()

    def created_at(image: dict[str, Any]) -> int:
        return int(image.get("created_at") or 0)

    eligible = [image for image in images if now - created_at(image) >= CLEANUP_GRACE_SECONDS]
    candidates = sorted(eligible or images, key=created_at)
    deleted = 0
    for image in candidates[: max(0, count)]:
        image_id = str(image.get("image_id") or "")
        if not image_id:
            continue
        await _api_request(bot, "DELETE", "media-images", image_id, "delete")
        _forget_cached_image(bot.self_id, image_id)
        deleted += 1
    return deleted


async def _upload_payload(bot: QQBot, payload: _ImagePayload) -> str:
    """上传已规范化的图片并返回 ``qqbot-media://`` 引用链接

    同一机器人上的相同图片会复用缓存；配额用满（40035007）时先清理最早上传的
    一批图片，再重试一次。
    """
    digest = hashlib.md5(payload.data, usedforsecurity=False).hexdigest()
    cache_key = (bot.self_id, digest)
    if cached := _CACHE.get(cache_key):
        _CACHE.move_to_end(cache_key)
        return cached.url

    try:
        url, image_id = await _upload_once(bot, payload, digest)
    except ActionFailed as e:
        if e.code != QUOTA_EXCEEDED_CODE:
            raise
        logger.warning("QQ 素材库图片数量已达上限，清理最早上传的图片后重试")
        await delete_oldest_images(bot)
        url, image_id = await _upload_once(bot, payload, digest)

    _CACHE[cache_key] = _CachedImage(image_id=image_id, url=url)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return url


async def upload_image(bot: QQBot, data: bytes) -> str:
    """规范化并上传图片，返回 ``qqbot-media://`` 引用链接"""
    return await _upload_payload(bot, normalize_image(data))


async def create_image_markdown(data: bytes, bot: QQBot) -> str:
    """上传图片到 QQ 素材库并生成 markdown 图片代码

    Args:
        data: 图片二进制数据（png/jpeg/gif/webp；其它格式会尝试转成 PNG）
        bot: 将要发送该 markdown 消息的 QQ 官方机器人，上传的图片只属于该机器人

    Returns:
        markdown 代码，如 ``![text #380px #760px](qqbot-media://image/v1/<token>)``
    """
    payload = normalize_image(data)
    url = await _upload_payload(bot, payload)
    code = build_image_markdown(url, payload.data)
    logger.debug(code)
    return code
