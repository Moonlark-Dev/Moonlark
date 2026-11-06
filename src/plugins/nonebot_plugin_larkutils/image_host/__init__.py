"""markdown 消息图床

支持两种模式，由 ``IMAGE_HOST_MODE`` 选择：

- ``object_storage``（默认）：把图片直传 S3 兼容对象存储（Cloudflare R2 / 腾讯云 COS 等），使用 ``R2_*`` 配置；
- ``self_hosted``：图片写入本地磁盘，由 nonebot 的 FastAPI app 直接提供访问，不需要任何 ``R2_*`` 配置，
  对外基础 URL 由 ``IMAGE_HOST_BASE_URL`` 独立配置。
"""

from .host import create_image_markdown as create_image_markdown

__all__ = ["create_image_markdown"]
