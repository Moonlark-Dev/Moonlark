#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

"""从 Message Summary 的消息记录里临时还原 QQ 群成员列表。

QQ 开放平台的群成员列表接口只对白名单机器人开放，实际调用时还可能因为配额、
权限或平台故障而失败（适配器会抛出 ``ActionFailed``）。这种情况下
``nonebot_plugin_message_summary`` 保存的群消息仍然能反映「最近在群里发过言的
用户」，因此这里把它作为群成员列表的临时降级数据源：

- 不写回 :class:`~nonebot_plugin_larkuser.models.QQGroupMember` 缓存，接口恢复后
  仍以腾讯返回的权威成员列表为准；
- ``GroupMessage.user_id`` 是 Moonlark 主账号 ID（QQ 官方消息会被 auto_bind
  归一化），与接口返回的 ``member_openid`` 不一定一致，因此这里只把结果当作临时的
  活跃用户列表使用；
- ``message_summary`` 插件 require 了 larkuser，因此只能在函数内延迟导入它的模型，
  插件未加载或表不存在时返回空列表。
"""

from datetime import datetime, timedelta
from typing import Optional

from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from .types import QQGroupMemberInfo

# Message Summary 只保留最近约两天的消息，降级时按同样的窗口统计活跃成员
MESSAGE_SUMMARY_FALLBACK_HOURS = 48
# QQ 官方 Bot 的群会话 ID 前缀，与 nonebot_plugin_session / larkutils.get_group_id 一致
QQ_GROUP_ID_PREFIX = "qq_"


def _load_group_message_model() -> Optional[type]:
    """延迟获取 Message Summary 的 ``GroupMessage`` 模型。"""
    try:
        from nonebot_plugin_message_summary.models import GroupMessage
    except ImportError:
        logger.debug("[larkuser] 未加载 message_summary 插件，无法从消息记录还原群成员")
        return None
    return GroupMessage


async def _query_message_summary_members(group_message_model: type, group_openid: str) -> list[QQGroupMemberInfo]:
    """按最近发言时间查询去重后的群成员，昵称取该成员最后一条消息的发送者昵称。"""
    GroupMessage = group_message_model
    since = datetime.now() - timedelta(hours=MESSAGE_SUMMARY_FALLBACK_HOURS)
    # 正常情况下消息记录里的 group_id 带平台前缀；同时兼容不带前缀的历史 / 其他写入方
    group_ids = (f"{QQ_GROUP_ID_PREFIX}{group_openid}", group_openid)
    async with get_session() as session:
        ranked = (
            await session.execute(
                select(
                    GroupMessage.user_id,
                    func.max(GroupMessage.id_).label("last_message_id"),
                )
                .where(GroupMessage.group_id.in_(group_ids))
                .where(GroupMessage.timestamp >= since)
                .where(GroupMessage.user_id.is_not(None))
                .group_by(GroupMessage.user_id)
                .order_by(func.max(GroupMessage.id_).desc()),
            )
        ).all()
        if not ranked:
            return []
        nicknames = dict(
            (
                await session.execute(
                    select(GroupMessage.user_id, GroupMessage.sender_nickname).where(
                        GroupMessage.id_.in_([row.last_message_id for row in ranked]),
                    ),
                )
            ).all(),
        )
    return [
        QQGroupMemberInfo(member_openid=str(row.user_id), nickname=nicknames.get(row.user_id) or "")
        for row in ranked
        if row.user_id
    ]


async def fetch_group_members_from_message_summary(group_openid: str) -> list[QQGroupMemberInfo]:
    """从 Message Summary 保存的群消息里临时还原一份群成员列表。

    返回按最近发言时间倒序排列的成员（最近发言的在前），没有任何可用记录或查询失败时
    返回空列表，调用方据此决定是否继续使用原有缓存。
    """
    try:
        group_message_model = _load_group_message_model()
        if group_message_model is None:
            return []
        return await _query_message_summary_members(group_message_model, group_openid)
    except Exception as e:
        logger.warning(f"[larkuser] 从 Message Summary 还原群 {group_openid} 成员失败: {e}")
        return []
