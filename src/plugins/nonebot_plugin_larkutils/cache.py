import secrets
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from aiobotocore.session import AioSession
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from nonebot import logger
from PIL import Image

from .config import config

DEFAULT_WIDTH = 208
DEFAULT_HEIGHT = 320


def _is_r2_configured() -> bool:
    return all(
        [
            config.r2_access_key_id,
            config.r2_secret_access_key,
            config.r2_bucket_name,
            config.r2_public_base_url,
        ],
    ) and bool(config.r2_account_id or config.r2_endpoint_url)


def _get_endpoint_url() -> str:
    if config.r2_endpoint_url:
        return config.r2_endpoint_url
    return f"https://{config.r2_account_id}.r2.cloudflarestorage.com"


def _create_client() -> Any:
    return AioSession().create_client(
        "s3",
        endpoint_url=_get_endpoint_url(),
        region_name=config.r2_region,
        aws_access_key_id=config.r2_access_key_id,
        aws_secret_access_key=config.r2_secret_access_key,
        config=Config(s3={"addressing_style": config.r2_addressing_style}),
    )


def _detect_image_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    if data.startswith(b"BM"):
        return "image/bmp", "bmp"
    return "image/png", "png"


async def _upload_to_r2(data: bytes, content_type: str, key: str) -> None:
    try:
        async with _create_client() as client:
            await client.put_object(
                Bucket=config.r2_bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"上传到 R2 失败: {e}") from e


async def _collect_expired_keys(cutoff: float) -> list[str]:
    expired: list[str] = []
    try:
        async with _create_client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=config.r2_bucket_name):
                expired.extend(
                    obj["Key"] for obj in page.get("Contents", []) if obj["LastModified"].timestamp() < cutoff
                )
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"列出 R2 对象失败: {e}") from e
    return expired


async def _delete_objects(keys: list[str]) -> None:
    if not keys:
        return
    async with _create_client() as client:
        for start in range(0, len(keys), 1000):
            chunk = [{"Key": key} for key in keys[start : start + 1000]]
            try:
                await client.delete_objects(Bucket=config.r2_bucket_name, Delete={"Objects": chunk})
            except (ClientError, BotoCoreError) as e:
                raise RuntimeError(f"删除 R2 对象失败: {e}") from e


async def create_image_markdown(data: bytes, image_id: str | None = None, ext: str | None = None) -> str:
    """原图直传 S3 兼容对象存储图床，并生成 QQ 适配器可用的 markdown 图片代码（不做压缩）

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据图片内容推断

    Returns:
        markdown 代码，如 ![text #380px #760px](https://pub-xxx.r2.dev/ab12cd34.png)
    """
    if not _is_r2_configured():
        raise RuntimeError(
            "S3 图床未配置：请设置 R2_ACCESS_KEY_ID、R2_SECRET_ACCESS_KEY、R2_BUCKET_NAME、R2_PUBLIC_BASE_URL，"
            "并设置 R2_ENDPOINT_URL 或 R2_ACCOUNT_ID 之一",
        )
    content_type, detected_ext = _detect_image_type(data)
    key = f"{image_id or secrets.token_hex(8)}.{ext or detected_ext}"
    await _upload_to_r2(data, content_type, key)
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
    except Exception:
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
    code = f"![text #{width}px #{height}px]({config.r2_public_base_url.rstrip('/')}/{key})"
    logger.debug(code)
    return code


async def _cleanup_expired() -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - config.r2_object_ttl
    expired = await _collect_expired_keys(cutoff)
    await _delete_objects(expired)
    return len(expired)


# async def _cleanup_task() -> None:
#     interval = max(3600, config.r2_object_ttl // 24)
#     while True:
#         try:
#             if count := await _cleanup_expired():
#                 logger.info(f"R2 图床已自动清理 {count} 个过期对象")
#         except Exception as e:
#             logger.exception(f"R2 图床自动清理失败: {e}")
#         await asyncio.sleep(interval)


# @get_driver().on_startup
# async def _() -> None:
#     if _is_r2_configured():
#         asyncio.create_task(_cleanup_task())
