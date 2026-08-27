import asyncio
import hashlib
import hmac
import secrets
from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree  # ruff: ignore[suspicious-xml-etree-import] (仅解析 R2 官方响应 XML)

import httpx
from nonebot import get_driver, logger

from .config import config

SERVICE = "s3"


def _is_r2_configured() -> bool:
    return all(
        [
            config.r2_account_id,
            config.r2_access_key_id,
            config.r2_secret_access_key,
            config.r2_bucket_name,
            config.r2_public_base_url,
        ],
    )


def _endpoint(key: str | None = None, query: dict[str, str] | None = None) -> str:
    url = f"https://{config.r2_account_id}.r2.cloudflarestorage.com/{config.r2_bucket_name}"
    if key is not None:
        url += f"/{quote(key, safe='-_.~')}"
    if query:
        url += "?" + "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(query.items()))
    return url


def _hmac_chain(secret: str, date_stamp: str, region: str) -> bytes:
    key = ("AWS4" + secret).encode()
    for value in (date_stamp, region, SERVICE, "aws4_request"):
        key = hmac.new(key, value.encode(), hashlib.sha256).digest()
    return key


def _sign_headers(method: str, url: str, payload: bytes, content_type: str | None = None) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(payload).hexdigest()
    parsed = urlsplit(url)
    headers = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        headers["content-type"] = content_type
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted(headers.items()))
    signed_headers = ";".join(sorted(headers))
    canonical_request = "\n".join(
        [
            method,
            quote(parsed.path, safe="/-_.~"),
            parsed.query,
            canonical_headers,
            "",
            signed_headers,
            payload_hash,
        ],
    )
    scope = f"{date_stamp}/{config.r2_region}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()],
    )
    signature = hmac.new(
        _hmac_chain(config.r2_secret_access_key, date_stamp, config.r2_region),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    sent_headers = {
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={config.r2_access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        sent_headers["content-type"] = content_type
    return sent_headers


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


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_local(root: ElementTree.Element, name: str) -> Iterator[ElementTree.Element]:
    return (el for el in root.iter() if _local_name(el.tag) == name)


def _parse_iso_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def _upload_to_r2(data: bytes, content_type: str, key: str) -> None:
    url = _endpoint(key)
    async with httpx.AsyncClient() as client:
        response = await client.put(url, content=data, headers=_sign_headers("PUT", url, data, content_type))
    if response.status_code >= 300:
        raise RuntimeError(f"上传到 R2 失败 ({response.status_code}): {response.text}")


async def _collect_expired_keys(client: httpx.AsyncClient, cutoff: float) -> list[str]:
    expired: list[str] = []
    token: str | None = None
    while True:
        query = {"list-type": "2", "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        url = _endpoint(query=query)
        response = await client.get(url, headers=_sign_headers("GET", url, b""))
        if response.status_code >= 300:
            raise RuntimeError(f"列出 R2 对象失败 ({response.status_code}): {response.text}")
        root = ElementTree.fromstring(response.content)  # ruff: ignore[suspicious-xml-element-tree-usage] (R2 官方响应，非不可信输入)
        for contents in _iter_local(root, "Contents"):
            key = next(iter(_iter_local(contents, "Key"))).text
            modified = next(iter(_iter_local(contents, "LastModified"))).text
            if _parse_iso_time(modified).timestamp() < cutoff:
                expired.append(key)
        token_elem = next((el for el in _iter_local(root, "IsTruncated")), None)
        if token_elem is None or token_elem.text != "true":
            break
        token = next(iter(_iter_local(root, "NextContinuationToken"))).text
    return expired


async def _delete_objects(client: httpx.AsyncClient, keys: list[str]) -> None:
    content_type = "application/xml"
    for start in range(0, len(keys), 1000):
        chunk = keys[start : start + 1000]
        body = "<Delete>" + "".join(f"<Object><Key>{_xml_escape(key)}</Key></Object>" for key in chunk) + "</Delete>"
        url = _endpoint(query={"delete": ""})
        response = await client.post(url, content=body, headers=_sign_headers("POST", url, body, content_type))
        if response.status_code >= 300:
            raise RuntimeError(f"删除 R2 对象失败 ({response.status_code}): {response.text}")


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


async def create_image_markdown(data: bytes, image_id: str | None = None, ext: str | None = None) -> str:
    """原图直传 Cloudflare R2 图床，并生成 QQ 适配器可用的 markdown 图片代码（不做压缩）

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据图片内容推断

    Returns:
        markdown 代码，如 ![text #0 #0](https://pub-xxx.r2.dev/ab12cd34.jpg)
    """
    if not _is_r2_configured():
        raise RuntimeError(
            "Cloudflare R2 未配置：请设置 R2_ACCOUNT_ID、R2_ACCESS_KEY_ID、R2_SECRET_ACCESS_KEY、R2_BUCKET_NAME、R2_PUBLIC_BASE_URL",
        )
    content_type, detected_ext = _detect_image_type(data)
    key = f"{image_id or secrets.token_hex(8)}.{ext or detected_ext}"
    await _upload_to_r2(data, content_type, key)
    code = f"![text #0 #0]({config.r2_public_base_url.rstrip('/')}/{key})"
    logger.debug(code)
    return code


async def _cleanup_expired() -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - config.r2_object_ttl
    async with httpx.AsyncClient() as client:
        expired = await _collect_expired_keys(client, cutoff)
        await _delete_objects(client, expired)
    return len(expired)


async def _cleanup_task() -> None:
    interval = max(3600, config.r2_object_ttl // 24)
    while True:
        try:
            if count := await _cleanup_expired():
                logger.info(f"R2 图床已自动清理 {count} 个过期对象")
        except Exception as e:
            logger.exception(f"R2 图床自动清理失败: {e}")
        await asyncio.sleep(interval)


@get_driver().on_startup
async def _() -> None:
    if _is_r2_configured():
        asyncio.create_task(_cleanup_task())
