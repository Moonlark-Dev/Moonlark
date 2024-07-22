from nonebot.params import Depends
from nonebot_plugin_alconna import UniMessage

from ...nonebot_plugin_render import render_template
from ...nonebot_plugin_larkutils import get_user_id
from ..__main__ import matcher, lang
from ..utils import get_user_durations, get_wakatime_name, get_user_ranking
from ..models import DurationsProject, DurationsResponse


async def get_durations(user_id: str = get_user_id()) -> DurationsResponse:
    if (name := await get_wakatime_name(user_id)) is None or (durations := await get_user_durations(name)) is None:
        await lang.finish("main.n", user_id)
        return DurationsResponse()
    if len(durations.data.projects) <= 0:
        durations.data.projects = [
            DurationsProject(name=await lang.text("main.none", user_id), text=await lang.text("main.zero", user_id))
        ]
    return durations


@matcher.assign("$main")
async def _(durations: DurationsResponse = Depends(get_durations), user_id: str = get_user_id()) -> None:
    image = await render_template(
        "wakatime.html.jinja",
        await lang.text("info.title", user_id),
        user_id,
        {
            "user_id": await lang.text("info.user_id", user_id, user_id),
            "wakatime": durations.data.username,
            "code_time": await lang.text(
                "info.code_time",
                user_id,
                durations.data.human_readable_total,
                durations.data.human_readable_total_including_other_language,
            ),
            "rank": await lang.text("info.rank", user_id, await get_user_ranking(user_id)),
            "time": await lang.text("info.time", user_id),
            "start": await lang.text("info.start", user_id, durations.data.start),
            "end": await lang.text("info.end", user_id, durations.data.end),
            "project": await lang.text(
                "info.project", user_id, durations.data.projects[0].name, durations.data.projects[0].text
            ),
        },
    )
    await matcher.finish(UniMessage().image(raw=image))
