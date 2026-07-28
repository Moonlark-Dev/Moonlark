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

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_auto_bind",
    description="Auto-bind QQ adapter OpenID to OneBot 11 User ID when detecting simultaneous messages",
    usage="",
)

require("nonebot_plugin_larkuser")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_orm")

from . import main  # ruff:ignore[module-import-not-at-top-of-file, unused-import]
