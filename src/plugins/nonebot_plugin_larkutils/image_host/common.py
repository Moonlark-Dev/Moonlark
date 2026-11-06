"""图床两种模式共用的图片处理逻辑"""

import secrets
from io import BytesIO

from PIL import Image

DEFAULT_WIDTH = 208
DEFAULT_HEIGHT = 320


def detect_image_type(data: bytes) -> tuple[str, str]:
    """根据文件头推断图片 MIME 类型与后缀名"""
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


def detect_image_size(data: bytes) -> tuple[int, int]:
    """读取图片尺寸，解析失败时回退到默认尺寸"""
    try:
        with Image.open(BytesIO(data)) as image:
            return image.size
    except Exception:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT


def build_image_name(data: bytes, image_id: str | None = None, ext: str | None = None) -> tuple[str, str]:
    """生成图床对象名与对应的 MIME 类型

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据图片内容推断

    Returns:
        (对象名, MIME 类型)
    """
    content_type, detected_ext = detect_image_type(data)
    return f"{image_id or secrets.token_hex(8)}.{ext or detected_ext}", content_type


def build_image_markdown(url: str, data: bytes) -> str:
    """生成 QQ 适配器可用的 markdown 图片代码（带渲染尺寸）"""
    width, height = detect_image_size(data)
    return f"![text #{width}px #{height}px]({url})"
