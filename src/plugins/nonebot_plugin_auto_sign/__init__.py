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
    name="自动签到",
    description="每天 23:55 消耗自动签到券代替用户完成签到，并通过邮件推送签到结果",
    usage="使用 /sign auto on 开启自动签到",
    type="application",
    homepage="https://github.com/Moonlark-Dev/Moonlark",
    supported_adapters={"~"},
)

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_email")
require("nonebot_plugin_bag")
require("nonebot_plugin_items")
require("nonebot_plugin_sign")

from . import __main__
