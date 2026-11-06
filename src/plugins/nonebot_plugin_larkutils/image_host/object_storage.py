"""对象存储模式：把图片直传 S3 兼容对象存储（Cloudflare R2 / 腾讯云 COS 等）"""

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from aiobotocore.session import AioSession
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ..config import config
from .common import build_image_name


def is_configured() -> bool:
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


def _is_cos_endpoint() -> bool:
    # 腾讯云 COS 的 S3 兼容端点域名（cos.<region>.myqcloud.com 等）
    hostname = urlsplit(_get_endpoint_url()).hostname
    return bool(hostname and hostname.endswith(".myqcloud.com"))


def _get_signature_version() -> str:
    if config.r2_signature_version != "auto":
        return config.r2_signature_version
    # 腾讯云官方文档要求 boto3 访问 COS 时使用 signature_version=s3（AWS SigV2）：
    # https://cloud.tencent.com/document/product/436/37421 。SigV4 在部分 COS 配置下会报
    # SignatureDoesNotMatch，因此对 *.myqcloud.com 端点自动选用 s3，其余端点保持默认 s3v4。
    return "s3" if _is_cos_endpoint() else "s3v4"


def _create_client() -> Any:
    return AioSession().create_client(
        "s3",
        endpoint_url=_get_endpoint_url(),
        region_name=config.r2_region,
        aws_access_key_id=config.r2_access_key_id,
        aws_secret_access_key=config.r2_secret_access_key,
        config=Config(
            signature_version=_get_signature_version(),
            s3={"addressing_style": config.r2_addressing_style},
        ),
    )


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


async def upload_image(data: bytes, image_id: str | None = None, ext: str | None = None) -> str:
    """原图直传 S3 兼容对象存储图床，返回图片可访问 URL（不做压缩）

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据图片内容推断
    """
    if not is_configured():
        raise RuntimeError(
            "S3 图床未配置：请设置 R2_ACCESS_KEY_ID、R2_SECRET_ACCESS_KEY、R2_BUCKET_NAME、R2_PUBLIC_BASE_URL，"
            "并设置 R2_ENDPOINT_URL 或 R2_ACCOUNT_ID 之一；或改用 IMAGE_HOST_MODE=self_hosted 使用自建图床",
        )
    key, content_type = build_image_name(data, image_id, ext)
    await _upload_to_r2(data, content_type, key)
    return f"{config.r2_public_base_url.rstrip('/')}/{key}"


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


def _inject_content_md5(params: dict[str, Any], **_: Any) -> None:
    """为 DeleteObjects 请求补充 Content-MD5 请求头

    腾讯云 COS 的 S3 兼容 API 强制要求该头，缺失时报
    InvalidRequest: Missing required header for this request: Content-MD5；
    AWS/R2 不要求，补充后无副作用。
    """
    if body := params.get("body"):
        # usedforsecurity=False：Content-MD5 仅为完整性校验，非安全用途（bandit B324 / ruff S324 均放行）
        digest = hashlib.md5(body, usedforsecurity=False).digest()
        params.setdefault("headers", {})["Content-MD5"] = base64.b64encode(digest).decode()


async def _delete_objects(keys: list[str]) -> None:
    if not keys:
        return
    async with _create_client() as client:
        client.meta.events.register("before-call.s3.DeleteObjects", _inject_content_md5)
        for start in range(0, len(keys), 1000):
            chunk = [{"Key": key} for key in keys[start : start + 1000]]
            try:
                await client.delete_objects(Bucket=config.r2_bucket_name, Delete={"Objects": chunk})
            except (ClientError, BotoCoreError) as e:
                raise RuntimeError(f"删除 R2 对象失败: {e}") from e


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
#     if is_configured():
#         asyncio.create_task(_cleanup_task())
