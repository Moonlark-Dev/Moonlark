from typing import Any, Literal

from nonebot import get_plugin_config
from pydantic import BaseModel, field_validator


class Config(BaseModel):
    """Plugin Config Here"""

    baidu_api_key: str
    baidu_secret_key: str
    superusers: set[str]
    # S3 兼容对象存储图床配置（create_image_markdown 使用）
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_base_url: str = ""
    # S3 兼容端点；为空且设置了 r2_account_id 时使用 Cloudflare R2 默认端点
    r2_endpoint_url: str = ""
    # S3 寻址风格：path（R2/MinIO 等）或 virtual（腾讯云 COS 等强制虚拟主机域名）
    r2_addressing_style: Literal["path", "virtual", "auto"] = "path"
    r2_region: str = "auto"
    # R2 对象自动清理过期时间（秒），默认 7 天
    r2_object_ttl: int = 604800
    command_start: list[str]

    @field_validator("r2_addressing_style", mode="before")
    @classmethod
    def _empty_addressing_style_to_default(cls, value: Any) -> Any:
        # `.env` 中该行留空（R2_ADDRESSING_STYLE=）时应回退到默认 path 寻址
        if value == "":
            return "path"
        return value


config = get_plugin_config(Config)
