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

from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_menupanel",
    description="QQ 自定义菜单与指令面板的网页配置支持",
    usage="超管在 moonlark-frontend 超级管理员面板选择对外展示的指令并同步到 QQ",
    config=Config,
)

require("nonebot_plugin_larkuid")
require("nonebot_plugin_larkhelp")
require("nonebot_plugin_localstore")

from . import web  # noqa: E402, F401
from .store import load_settings, save_settings  # noqa: E402, F401
