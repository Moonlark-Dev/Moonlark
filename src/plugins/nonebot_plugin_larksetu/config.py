from typing import Optional

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    setu_cd: int = 20
    # 可用池中保持的图片数量
    setu_cache_count: int = 10
    # 已发放图片（例如签到卡片头图）保留原图的时长（秒），期间可用 #setu-g 查看原图
    setu_cache_ttl: int = 3600
    setu_proxy: Optional[str] = None
    setu_retry_time: int = 3


config = get_plugin_config(Config)
