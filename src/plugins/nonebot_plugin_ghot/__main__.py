from nonebot.adapters import Event
from nonebot_plugin_alconna import Alconna, Arparma, Option, Subcommand, UniMessage, on_alconna
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session

from .utils.group import resolve_group_keys
from .utils.image import render_heat_chart, render_line_chart
from .utils.ranking import get_all_groups_scores, get_group_rankings
from .utils.score import get_group_hot_score
from .lang import lang

ghot_cmd = on_alconna(
    Alconna(
        "ghot",
        Subcommand("history", Option("-l|--line")),
    )
)


@ghot_cmd.assign("$main")
async def handle_ghot_command(
    _event: Event,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    # 同一物理群在 QQ 官方（group_openid）与 OneBot（群号）下是两个群键，这里合并
    group_keys = await resolve_group_keys(session, group_id)

    # Get scores for current group
    scores = await get_group_hot_score(group_keys, session)

    # Get scores for all groups
    all_scores = await get_all_groups_scores(session)

    # Get rankings for current group
    rankings = await get_group_rankings(all_scores, group_keys[0])

    # Format response
    response = await lang.text(
        "ghot.response",
        user_id,
        scores[0],
        scores[1],
        scores[2],  # 1min, 5min, 15min scores
        rankings[0],
        rankings[1],
        rankings[2],  # 1min, 5min, 15min rankings
    )

    await ghot_cmd.finish(response)


@ghot_cmd.assign("history")
async def _(
    arparam: Arparma,
    _event: Event,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """
    Handle /ghot history command to show group heat score history chart.
    """
    group_keys = await resolve_group_keys(session, group_id)
    if "line" in arparam.subcommands["history"].options:
        raw = await render_line_chart(session, user_id, group_keys)
    else:
        raw = await render_heat_chart(session, user_id, group_keys)
    # Send the chart
    await ghot_cmd.finish(UniMessage().image(raw=raw))
