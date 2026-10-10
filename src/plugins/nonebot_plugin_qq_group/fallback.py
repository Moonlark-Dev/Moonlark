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

- 不写回 :class:`~nonebot_plugin_qq_group.models.QQGroupMember` 缓存，接口恢复后
  仍以腾讯返回的权威成员列表为准；
- 优先使用 ``GroupMessage.platform_user_id``（即 ``event.get_user_id()``）：QQ 官方
  消息里它就是 ``member_openid``，能直接对上接口返回的成员；历史数据没有这一列时
  退回 Moonlark 主账号 ID（``GroupMessage.user_id``）；
- ``message_summary`` 插件 require 了本插件与 larkuser，因此只能在函数内延迟导入它的
  模型，插件未加载或表不存在时返回空列表。
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
        logger.debug("[qq_group] 未加载 message_summary 插件，无法从消息记录还原群成员")
        return None
    return GroupMessage


async def _query_message_summary_members(group_message_model: type, group_openid: str) -> list[QQGroupMemberInfo]:
    """按最近发言时间查询去重后的群成员，昵称取该成员最后一条消息的发送者昵称。"""
    GroupMessage = group_message_model
    since = datetime.now() - timedelta(hours=MESSAGE_SUMMARY_FALLBACK_HOURS)
    # 正常情况下消息记录里的 group_id 带平台前缀；同时兼容不带前缀的历史 / 其他写入方
    group_ids = (f"{QQ_GROUP_ID_PREFIX}{group_openid}", group_openid)
    # platform_user_id 才是适配器原生 ID（QQ 官方群里即 member_openid），
    # 没有它的历史记录退回主账号 ID，只作为活跃用户列表使用
    member_id = func.coalesce(GroupMessage.platform_user_id, GroupMessage.user_id).label("member_id")
    async with get_session() as session:
        ranked = (
            await session.execute(
                select(
                    member_id,
                    func.max(GroupMessage.id_).label("last_message_id"),
                )
                .where(GroupMessage.group_id.in_(group_ids))
                .where(GroupMessage.timestamp >= since)
                .where(member_id.is_not(None))
                .group_by(member_id)
                .order_by(func.max(GroupMessage.id_).desc()),
            )
        ).all()
        if not ranked:
            return []
        nicknames = dict(
            (
                await session.execute(
                    select(member_id, GroupMessage.sender_nickname).where(
                        GroupMessage.id_.in_([row.last_message_id for row in ranked]),
                    ),
                )
            ).all(),
        )
    return [
        QQGroupMemberInfo(member_openid=str(row.member_id), nickname=nicknames.get(row.member_id) or "")
        for row in ranked
        if row.member_id
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
        logger.warning(f"[qq_group] 从 Message Summary 还原群 {group_openid} 成员失败: {e}")
        return []
