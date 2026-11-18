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
from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """LarkHelp 插件配置"""

    # 是否启用帮助面板磁盘缓存与后台定时刷新
    larkhelp_cache: bool = True
    # 帮助面板热门指令榜单与缓存的后台刷新间隔（秒），默认 30 分钟；<= 0 表示关闭定时刷新
    larkhelp_cache_refresh_interval: int = 1800


config = get_plugin_config(Config)
