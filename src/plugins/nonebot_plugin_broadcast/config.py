from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """nonebot_plugin_broadcast Config（复用全局 superusers 判断公告发布权限）"""

    superusers: list[str] = []


config = get_plugin_config(Config)
