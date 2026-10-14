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
    name="nonebot_plugin_updates",
    description="更新公告发布与查看支持",
    usage="超管在 moonlark-frontend 发布 markdown 更新公告；用户可通过 /updates 指令查看最新公告",
    config=Config,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
require("nonebot_plugin_larkuid")

from . import web  # noqa: E402, F401
from .store import load_announcement, save_announcement  # noqa: E402
from .utils import has_new_update, mark_update_read  # noqa: E402
