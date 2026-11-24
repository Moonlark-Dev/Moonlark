"""收益排行榜的图片渲染与 Web API 接入。

排行榜统一交给 ``nonebot_plugin_ranking`` 绘制（``generate_image``），并把同一份
排序数据注册成 ``WebRanking``，Web 端 ``/api/rankings`` 会自动发现它。
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import RankingData, WebRanking, generate_image, register

from .config import config
from .market import ensure_market, load_ranking, market_lock, now_local

if TYPE_CHECKING:
    from .market import RankingEntry

logger = getLogger(__name__)
lang = LangHelper()


def _fmt_signed(value: float) -> str:
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:+.2f}"


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


async def ranking_entry_data(entry: RankingEntry, user_id: str) -> RankingData:
    """把一行排行数据转成 ranking 插件的数据结构

    ``data`` 参与排序（总收益率百分比），``display`` 覆盖展示值，
    ``info`` 是昵称下方的第二行说明。
    """
    rate = entry.return_rate * 100
    return {
        "user_id": entry.user_id,
        "data": round(rate, 2),
        "display": f"{_fmt_signed(rate)}%",
        "info": await lang.text(
            "rank.info",
            user_id,
            bought=_fmt_money(entry.total_bought),
            sold=_fmt_money(entry.total_sold),
        ),
    }


async def load_ranking_entries() -> list[RankingEntry]:
    """补算行情到当前时刻后读取收益率排行（与下单共用一把锁，保证价格一致）"""
    async with market_lock:
        async with get_session() as session:
            state = await ensure_market(session, now_local())
            entries = await load_ranking(session, state.price)
            await session.commit()
    return entries


async def render_ranking_image(entries: list[RankingEntry], user_id: str) -> bytes | None:
    """用 ranking 插件渲染排行榜图片；渲染失败返回 None，由调用方回退到文本"""
    try:
        title = await lang.text("rank.title", user_id)
        return await generate_image(
            [await ranking_entry_data(entry, user_id) for entry in entries],
            user_id,
            title,
            limit=max(1, config.trade_rank_size),
        )
    except Exception:
        logger.exception("渲染收益排行榜失败，回退到文本消息")
        return None


class TradeRanking(WebRanking):
    """Web 端收益排行榜：数据来源与指令侧完全一致"""

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        entries = await load_ranking_entries()
        return [await ranking_entry_data(entry, user_id) for entry in entries]


trade_ranking = TradeRanking("trade", "rank.web_name", lang)
register(trade_ranking)
