from nonebot.adapters import Event
from nonebot_plugin_alconna import Alconna, UniMessage, on_alconna
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session

from .utils.group import resolve_group_keys
from .utils.image import render_ghot_card
from .utils.ranking import get_all_groups_scores, get_group_rankings
from .utils.score import get_group_hot_score

ghot_cmd = on_alconna(Alconna("ghot"))


@ghot_cmd.handle()
async def handle_ghot_command(
    _event: Event,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """`ghot` 输出一张合并卡片：当前热度分数与排名 + 历史热度走势（原 `ghot history`）。"""
    # 同一物理群在 QQ 官方（group_openid）与 OneBot（群号）下是两个群键，这里合并
    group_keys = await resolve_group_keys(session, group_id)

    # Get scores for current group
    scores = await get_group_hot_score(group_keys, session)

    # Get scores for all groups
    all_scores = await get_all_groups_scores(session)

    # Get rankings for current group
    rankings = await get_group_rankings(all_scores, group_keys[0])

    # Render the merged card image
    raw = await render_ghot_card(session, user_id, group_keys, scores, rankings)

    await ghot_cmd.finish(UniMessage().image(raw=raw))
