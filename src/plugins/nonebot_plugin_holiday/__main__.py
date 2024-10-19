#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

from nonebot_plugin_alconna import UniMessage
from nonebot import on_command
from ..nonebot_plugin_preview.preview import screenshot
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id

matcher = on_command("holiday")
viewport = {"width": 1440, "height": 900}
lang = LangHelper()


@matcher.handle()
async def _(user_id: str = get_user_id()) -> None:
    try:
        msg = (
            UniMessage()
            .image(raw=await screenshot("https://xiayigejiaqi.com/balance?from=itab", viewport=viewport))
            .image(raw=await screenshot("https://xiayigejiaqi.com/?from=itab", viewport=viewport))
        )
    except Exception:
        await lang.finish("error.failed", user_id)
    await matcher.finish(await msg.export())
