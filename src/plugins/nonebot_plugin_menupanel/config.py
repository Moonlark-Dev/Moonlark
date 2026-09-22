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

from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """NoneBot Plugin MenuPanel Config"""

    superusers: list[str] = []
    # 前端在线帮助页地址，用于 QQ 自定义菜单的 link 菜单项
    menupanel_frontend_help_url: str = "https://moonlark.itcdt.top/#/help"
    # 同步到 QQ 的指令面板备注（用于识别 Moonlark 创建的面板）
    menupanel_panel_remark: str = "moonlark-menupanel"


config = get_plugin_config(Config)
