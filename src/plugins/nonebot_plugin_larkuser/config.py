from pydantic import BaseModel, Field
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    user_registered_guest: bool = False

    # ── QQ 官方 Bot 群聊缓存 ──
    # 是否启用群信息 / 群成员列表的周期性同步
    qq_group_sync_enabled: bool = True
    # 周期性同步任务的执行间隔（秒），默认 30 分钟
    qq_group_sync_interval: int = Field(default=1800, ge=60)
    # 群成员列表缓存的有效期（秒），超过后由周期任务重新拉取，默认 1 小时
    qq_group_member_cache_ttl: int = Field(default=3600, ge=60)
    # 群基本信息缓存的有效期（秒），默认 6 小时
    qq_group_info_cache_ttl: int = Field(default=21600, ge=60)
    # 单个群一次同步最多缓存的成员数，防止游标异常时无限翻页
    qq_group_member_max_count: int = Field(default=3000, ge=1)


config = get_plugin_config(Config)
