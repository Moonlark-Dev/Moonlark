import asyncio
import secrets
import time
from io import BytesIO

from fastapi import HTTPException, Response, status
from nonebot import get_app, get_driver, logger
from PIL import Image

from .config import config

app = get_app()

DEFAULT_CONTENT_TYPE = "image/png"

_CONTENT_TYPE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
}

_cache: dict[str, tuple[bytes, str, float]] = {}


def _now() -> float:
    return time.monotonic()


def _is_expired(entry: tuple[bytes, str, float]) -> bool:
    return _now() > entry[2]


def _prune() -> None:
    for image_id in [image_id for image_id, entry in _cache.items() if _is_expired(entry)]:
        del _cache[image_id]


def _generate_id(ext: str) -> str:
    while True:
        image_id = secrets.token_hex(8)
        key = f"{image_id}.{ext}"
        if key not in _cache:
            return key


async def add_image_to_cache(
    data: bytes,
    content_type: str = DEFAULT_CONTENT_TYPE,
    image_id: str | None = None,
    ext: str | None = None,
) -> str:
    """添加图片到内存图床，返回外部访问链接

    Args:
        data: 图片二进制数据
        content_type: 图片 MIME 类型
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据 content_type 推断

    Returns:
        外部访问链接，如 http://localhost:8080/cache/{image_id}.png
    """
    _prune()
    ext = ext or _CONTENT_TYPE_EXTENSIONS.get(content_type, "png")
    key = f"{image_id or _generate_id(ext)}.{ext}"
    _cache[key] = (data, content_type, _now() + config.image_cache_ttl)
    url = f"{config.moonlark_api_base}/cache/{key}"
    logger.debug(url)
    return url


async def _compress_to_jpeg(data: bytes, quality: int) -> bytes:
    with Image.open(BytesIO(data)) as image:
        if image.format == "JPEG":
            return data
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        buffer = BytesIO()
        background.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()


async def create_image_markdown(
    data: bytes,
    image_id: str | None = None,
    ext: str | None = None,
    quality: int = 85,
) -> str:
    """压缩图片为 JPEG 后上传到内存图床，并生成 QQ 适配器可用的 markdown 图片代码

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则推断为 jpg
        quality: JPEG 压缩质量（1-100）；原图为 JPEG 时不重复压缩

    Returns:
        markdown 代码，如 ![text #380px #760px](http://localhost:8080/cache/xxx.jpg)
    """
    data = await _compress_to_jpeg(data, quality)
    url = await add_image_to_cache(data, "image/jpeg", image_id, ext or "jpg")
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
    code = f"![text #0 #0]({url})"
    logger.debug(code)
    return code


@app.get("/cache/{image_id}")
async def get_image(image_id: str) -> Response:
    entry = _cache.get(image_id)
    if entry is None or _is_expired(entry):
        _cache.pop(image_id, None)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    data, content_type, _ = entry
    return Response(content=data, media_type=content_type)


async def _cleanup_task() -> None:
    interval = max(1, config.image_cache_ttl // 2)
    while True:
        await asyncio.sleep(interval)
        _prune()


@get_driver().on_startup
async def _() -> None:
    asyncio.create_task(_cleanup_task())
