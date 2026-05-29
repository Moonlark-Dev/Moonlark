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

from datetime import datetime, timedelta

from nonebot import logger
from nonebot.message import run_preprocessor
from nonebot.typing import T_State
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import on_alconna, Args, Arparma, UniMessage
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_render import render_template
from sqlalchemy import select, func, desc, distinct

from .models import CommandUsage

lang = LangHelper()


# ============================================================
# 自动记录指令使用（复用 status_report 的 run_preprocessor 模式）
# ============================================================

@run_preprocessor
async def record_command_usage(matcher: Matcher, state: T_State, event: Event) -> None:
    """自动记录所有指令使用到数据库"""
    # 识别指令名（参考 status_report 的逻辑）
    try:
        if hasattr(matcher, 'command') and callable(matcher.command):
            # AlconnaMatcher
            command_name = matcher.command().command
        elif matcher.type == "message":
            try:
                command_name = list(matcher.rule.checkers)[0].call.cmds[0][0]
            except Exception:
                return
        else:
            return
    except Exception:
        return

    # 跳过自身指令，避免死循环
    if command_name in ("指令排行", "cmd-rank", "命令排行", "热门指令"):
        return

    # 获取用户和群信息
    try:
        user_id = event.get_user_id()
    except Exception:
        user_id = "unknown"

    try:
        group_id = get_group_id()
    except Exception:
        group_id = None

    # 写入数据库
    try:
        async with get_session() as session:
            usage = CommandUsage(
                command=command_name,
                user_id=user_id,
                group_id=group_id,
                used_at=datetime.now(),
            )
            session.add(usage)
            await session.commit()
            logger.debug(f"[CommandStats] Recorded: /{command_name} by {user_id}")
    except Exception as e:
        logger.warning(f"[CommandStats] Failed to record command usage: {e}")


# ============================================================
# 查询指令排行
# ============================================================

async def get_command_ranking(days: int = 7, limit: int = 10) -> list[dict]:
    """获取近N天热门指令排行"""
    cutoff = datetime.now() - timedelta(days=days)

    async with get_session() as session:
        result = await session.execute(
            select(
                CommandUsage.command,
                func.count(CommandUsage.id).label("count"),
                func.count(distinct(CommandUsage.user_id)).label("user_count"),
            )
            .where(CommandUsage.used_at >= cutoff)
            .group_by(CommandUsage.command)
            .order_by(desc("count"))
            .limit(limit)
        )
        rows = result.all()

    return [
        {
            "rank": i + 1,
            "command": row.command,
            "count": row.count,
            "user_count": row.user_count,
        }
        for i, row in enumerate(rows)
    ]


async def get_total_stats(days: int = 7) -> dict:
    """获取总体统计数据"""
    cutoff = datetime.now() - timedelta(days=days)

    async with get_session() as session:
        # 总使用次数
        total_result = await session.execute(
            select(func.count(CommandUsage.id))
            .where(CommandUsage.used_at >= cutoff)
        )
        total_count = total_result.scalar() or 0

        # 独立用户数
        user_result = await session.execute(
            select(func.count(distinct(CommandUsage.user_id)))
            .where(CommandUsage.used_at >= cutoff)
        )
        user_count = user_result.scalar() or 0

        # 独立指令数
        cmd_result = await session.execute(
            select(func.count(distinct(CommandUsage.command)))
            .where(CommandUsage.used_at >= cutoff)
        )
        cmd_count = cmd_result.scalar() or 0

    return {
        "total_count": total_count,
        "user_count": user_count,
        "cmd_count": cmd_count,
    }


# ============================================================
# 指令注册
# ============================================================

cmd_rank = on_alconna(
    Args["days?", int],
    aliases={"指令排行", "cmd-rank", "命令排行", "热门指令"},
    priority=5,
)


@cmd_rank.handle()
async def handle_cmd_rank(result: Arparma, user_id: str = get_user_id()):
    days = result.query("days", default=7)
    if days < 1 or days > 90:
        await cmd_rank.finish(await lang.text("ranking.days_error", user_id))

    ranking = await get_command_ranking(days=days, limit=10)
    stats = await get_total_stats(days=days)

    if not ranking:
        await cmd_rank.finish(await lang.text("ranking.no_data", user_id, days))

    # 渲染图片
    title = await lang.text("ranking.title", user_id, days)
    image = await render_template(
        "command_ranking.html.jinja",
        title,
        user_id,
        {
            "days": days,
            "ranking": ranking,
            "stats": stats,
            "text": {
                "total_count": await lang.text("ranking.total_count", user_id),
                "cmd_count": await lang.text("ranking.cmd_count", user_id),
                "user_count": await lang.text("ranking.user_count", user_id),
                "user_detail": await lang.text("ranking.user_detail", user_id),
                "count_unit": await lang.text("ranking.count_unit", user_id),
            },
        },
    )

    await cmd_rank.finish(UniMessage().image(raw=image))
