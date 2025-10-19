from nonebot_plugin_alconna import Alconna, Arparma, Option, on_alconna, Subcommand, UniMessage

from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_ghot.utils.image import render_heat_cheat, render_line_cheat
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session
from nonebot.adapters.onebot.v11 import GroupMessageEvent

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
    _event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    # Get scores for current group
    scores = await get_group_hot_score(group_id, session)

    # Get scores for all groups
    all_scores = await get_all_groups_scores(session)

    # Get rankings for current group
    rankings = await get_group_rankings(all_scores, group_id)

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
    _event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """
    Handle /ghot history command to show group heat score history chart.
    """
    if "line" in arparam.subcommands["history"].options:
        raw = await render_line_cheat(session, user_id, group_id)
    else:
        raw = await render_heat_cheat(session, user_id, group_id)
    # Send the chart
    await ghot_cmd.finish(UniMessage().image(raw=raw))
