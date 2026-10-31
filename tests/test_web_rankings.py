"""排行榜接入 WebRanking 的注册回归测试。

插件导入必须发生在测试函数内部（collection 阶段 nonebot 插件尚未加载）。
"""

import pytest

# 本次接入的排行榜 id；遗漏注册时这些接口不会出现在 /api/rankings 列表里
EXPECTED_RANKING_IDS = {
    "fav",
    "online_timer",
    "wakeuprank",
    "wakeuprank_avg",
    "splat",
    "splat_throwers",
    "chatterbox",
    "jrrp",
    "rua",
    "mvp",
}


@pytest.mark.asyncio
async def test_rankings_are_registered() -> None:
    from nonebot_plugin_ranking.web import rankings

    registered = {ranking.get_id() for ranking in rankings}
    assert EXPECTED_RANKING_IDS <= registered


@pytest.mark.asyncio
async def test_ranking_ids_are_unique() -> None:
    from nonebot_plugin_ranking.web import rankings

    ids = [ranking.get_id() for ranking in rankings]
    assert len(ids) == len(set(ids))
