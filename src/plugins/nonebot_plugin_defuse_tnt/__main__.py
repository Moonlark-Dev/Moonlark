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

from nonebot_plugin_alconna import Alconna, on_alconna
import random
from nonebot_plugin_waiter import prompt
from nonebot.log import logger
from src.plugins.nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_alconna import UniMessage
from src.plugins.nonebot_plugin_render import render_template
import re
from src.plugins.nonebot_plugin_defuse_tnt.utils import get_failed_result_string
from ..nonebot_plugin_larklang import LangHelper

lang = LangHelper()
alc = Alconna("defuse-tnt")
matcher = on_alconna(alc)


@matcher.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    answer = [random.randint(1, 9) for i in range(3)]
    logger.debug(f"Defuse TNT Answer: {answer}")
    r = 6
    history = []
    while r >= 0:
        image = await render_template(
            "defuseTNT.html.jinja",
            await lang.text("template.main_title", user_id),
            user_id,
            {
                "title": await lang.text("template.title", user_id),
                "input": await lang.text("template.input", user_id),
                "remain": await lang.text("template.remain", user_id, r),
                "table_number": await lang.text("template.table_number", user_id),
                "table_passwd": await lang.text("template.table_passwd", user_id),
                "table_result": await lang.text("template.table_result", user_id),
                "history": [
                    {"password": item, "result": await get_failed_result_string(item, answer, user_id)}
                    for item in history
                ],
            },
        )
        message = await prompt(await UniMessage.image(raw=image).export())
        if message is None:
            continue
        password = [int(c) for c in list(message.extract_plain_text()) if re.match("[1-9]", c)]
        if len(password) != 3:
            continue
        if password == answer:
            await lang.finish("result.success", user_id)
        else:
            history.append(password)
            await matcher.send(await get_failed_result_string(password, answer, user_id))
            r -= 1
    await lang.finish("result.failed", user_id, answer)
