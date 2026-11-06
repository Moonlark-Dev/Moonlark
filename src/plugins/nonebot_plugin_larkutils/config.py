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
    # S3 签名版本：s3v4（AWS SigV4，Cloudflare R2 等默认）或 s3（AWS SigV2，腾讯云 COS 官方文档要求）；
    # 默认 auto 时自动选择：*.myqcloud.com（腾讯云 COS）端点使用 s3，其余端点使用 s3v4
    r2_signature_version: Literal["auto", "s3v4", "s3"] = "auto"
    r2_region: str = "auto"
    # R2 对象自动清理过期时间（秒），默认 7 天
    r2_object_ttl: int = 604800
    # markdown 消息图床模式：object_storage=S3 兼容对象存储（Cloudflare R2 / 腾讯云 COS 等）；
    # self_hosted=自建图床，由 nonebot 的 FastAPI app 直接提供图片访问，不需要任何 R2_* 配置
    image_host_mode: Literal["object_storage", "self_hosted"] = "object_storage"
    # 自建图床对外可访问的基础 URL，独立于 MOONLARK_API_BASE；如 https://bot.example.com
    image_host_base_url: str = ""
    # 自建图床在 FastAPI app 中的路由前缀
    image_host_route: str = "/image-host"
    # 自建图床图片存储目录；留空时使用 localstore 的缓存目录
    image_host_storage_dir: str = ""
    # 自建图床图片保留时间（秒），默认 7 天；<=0 表示不自动清理
    image_host_object_ttl: int = 604800
    command_start: list[str]

    @field_validator("image_host_mode", mode="before")
    @classmethod
    def _empty_image_host_mode_to_default(cls, value: Any) -> Any:
        # `.env` 中该行留空（IMAGE_HOST_MODE=）时应回退到默认的对象存储模式
        if value == "":
            return "object_storage"
        return value

    @field_validator("image_host_route", mode="before")
    @classmethod
    def _normalize_image_host_route(cls, value: Any) -> Any:
        # 统一为以 / 开头的路径；留空或 "/" 时回退到默认 /image-host
        route = str(value or "").strip().strip("/")
        return f"/{route}" if route else "/image-host"

    @field_validator("image_host_object_ttl", mode="before")
    @classmethod
    def _empty_image_host_object_ttl_to_default(cls, value: Any) -> Any:
        # `.env` 中该行留空（IMAGE_HOST_OBJECT_TTL=）时应回退到默认 7 天
        if value == "":
            return 604800
        return value

    @field_validator("r2_addressing_style", mode="before")
    @classmethod
    def _empty_addressing_style_to_default(cls, value: Any) -> Any:
        # `.env` 中该行留空（R2_ADDRESSING_STYLE=）时应回退到默认 path 寻址
        if value == "":
            return "path"
        return value

    @field_validator("r2_signature_version", mode="before")
    @classmethod
    def _empty_signature_version_to_default(cls, value: Any) -> Any:
        # `.env` 中该行留空（R2_SIGNATURE_VERSION=）时应回退到默认 auto
        if value == "":
            return "auto"
        return value


config = get_plugin_config(Config)
