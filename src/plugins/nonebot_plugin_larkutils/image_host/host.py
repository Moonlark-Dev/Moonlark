"""markdown 消息图床

支持两种模式，由 ``IMAGE_HOST_MODE`` 选择：

- ``object_storage``（默认）：把图片直传 S3 兼容对象存储（Cloudflare R2 / 腾讯云 COS 等），使用 ``R2_*`` 配置；
- ``self_hosted``：图片写入本地磁盘，由 nonebot 的 FastAPI app 直接提供访问，不需要任何 ``R2_*`` 配置，
  对外基础 URL 由 ``IMAGE_HOST_BASE_URL`` 独立配置。
"""

from nonebot import logger

from ..config import config
from . import object_storage, self_hosted
from .common import build_image_markdown

if config.image_host_mode == "self_hosted":
    self_hosted.register_image_route()


async def create_image_markdown(data: bytes, image_id: str | None = None, ext: str | None = None) -> str:
    """上传图片并生成 QQ 适配器可用的 markdown 图片代码（不做压缩）

    Args:
        data: 图片二进制数据
        image_id: 自定义 ID（不含后缀名）；不传则由系统随机生成
        ext: 文件后缀名；不传则根据图片内容推断

    Returns:
        markdown 代码，如 ![text #380px #760px](https://img.example.com/image-host/ab12cd34.png)
    """
    if config.image_host_mode == "self_hosted":
        url = await self_hosted.upload_image(data, image_id=image_id, ext=ext)
    else:
        url = await object_storage.upload_image(data, image_id=image_id, ext=ext)
    code = build_image_markdown(url, data)
    logger.debug(code)
    return code
