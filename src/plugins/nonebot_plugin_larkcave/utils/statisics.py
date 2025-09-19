#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
from io import BytesIO
from nonebot import logger
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from ..lang import lang
from ..models import CaveData
from nonebot_plugin_larkuser import get_user


from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager

font_manager.fontManager.addfont(Path(".").joinpath("src/static/SarasaGothicSC-Regular.ttf"))
plt.rcParams["font.sans-serif"] = ["Sarasa Gothic SC"]
plt.rcParams["axes.unicode_minus"] = False




async def get_poster_data(session: async_scoped_session) -> dict[str, int]:
    posters = {}
    for poster in await session.scalars(select(CaveData.author).where(CaveData.public == True)):
        if poster in posters:
            posters[poster] += 1
        else:
            posters[poster] = 1
    return posters


async def set_nickname_for_posters(data: dict[str, int], sender_id: str) -> dict[str, int]:
    other_key_name = await lang.text("stat.other", sender_id)
    posters = {}
    for user_id, count in data.items():
        user = await get_user(user_id)
        if not user.has_nickname():
            posters[other_key_name] = count + posters.get(other_key_name, 0)
            continue
        nickname = user.get_nickname()
        posters[nickname] = count + posters.get(nickname, 0)
    return posters


async def merge_small_poster(data: dict[str, int], sender_id: str) -> dict[str, int]:
    posters = {}
    lowest = sum([i for i in data.values()]) * 0.01
    other_key_name = await lang.text("stat.other", sender_id)
    for key, count in data.items():
        if key == other_key_name:
            continue
        elif count < lowest:
            posters[other_key_name] = count + posters.get(other_key_name, 0)
        else:
            posters[key] = count
    logger.debug(str(posters))
    return posters


async def render_pie(data, sender_id):
    absolute_value = lambda pct: int(pct / 100.0 * sum(data.values()))
    labels = list(data.keys())
    sizes = list(data.values())
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct=absolute_value, startangle=90)
    ax.set_title(await lang.text("stat.title", sender_id))
    ax.axis("equal")
    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
