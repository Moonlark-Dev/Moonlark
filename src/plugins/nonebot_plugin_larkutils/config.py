from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    baidu_api_key: str
    baidu_secret_key: str
    superusers: set[str]
    # Cloudflare R2 图床配置（create_image_markdown 使用）
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_base_url: str = ""
    r2_region: str = "auto"
    # R2 对象自动清理过期时间（秒），默认 7 天
    r2_object_ttl: int = 604800


config = get_plugin_config(Config)
