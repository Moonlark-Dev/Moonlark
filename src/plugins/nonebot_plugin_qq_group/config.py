#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from pydantic import BaseModel, Field
from nonebot import get_plugin_config


class Config(BaseModel):
    """QQ 官方 Bot 群聊缓存配置"""

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
