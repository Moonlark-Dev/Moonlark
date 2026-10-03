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

"""群聊会话元数据：最近发言者与主人存在指示。

``MessageProcessor.generate_session_info`` 在群聊会话创建/重置时调用这里，把
「当前会话成员/最近发言者」与「主人是否在当前会话」两行注入会话信息；私聊不会
调用这里，因此这两项在私聊中均不生效。

数据来自 nonebot_plugin_message_summary 的 GroupMessage 表——它只保留最近约两天
的消息，所以主人判定结果会落库到 ``ChatGroup.master_present`` 并只增不减：一旦
为 True，除非手动修改数据库，否则不会重新变回 False。
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import func, or_, select

from ..config import config
from ..models import ChatGroup

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# 最近发言者统计窗口（小时）与最多展示的人数
RECENT_SPEAKER_HOURS = 12
RECENT_SPEAKER_LIMIT = 5
# 主人的展示名，与 src/prompt/identity.md.jinja 中的称呼保持一致
MASTER_DISPLAY_NAME = "XiaoDeng3386"


def _load_group_message_model() -> Optional[type]:
    """延迟获取 Message Summary 的 GroupMessage 模型

    message_summary 插件 require 了 chat 插件，所以在 chat 里只能延迟导入；
    插件未加载时返回 None，调用方跳过相关元数据。
    """
    try:
        from nonebot_plugin_message_summary.models import GroupMessage
    except ImportError:
        logger.debug("[session_metadata] 未加载 message_summary 插件，跳过会话元数据统计")
        return None
    return GroupMessage


async def _query_recent_speakers(
    session: "AsyncSession",
    group_message_model: type,
    group_id: str,
    hours: int,
    limit: int,
) -> list[str]:
    """查询最近 hours 小时内发言最多的前 limit 位成员昵称（按发言条数降序）"""
    since = datetime.now() - timedelta(hours=hours)
    GroupMessage = group_message_model
    ranked = (
        await session.execute(
            select(
                GroupMessage.user_id,
                func.count().label("message_count"),
                func.max(GroupMessage.id_).label("last_message_id"),
            )
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.timestamp >= since)
            .where(GroupMessage.user_id.is_not(None))
            .group_by(GroupMessage.user_id)
            .order_by(func.count().desc(), func.max(GroupMessage.id_).desc())
            .limit(limit)
        )
    ).all()
    if not ranked:
        return []

    nicknames = dict(
        (
            await session.execute(
                select(GroupMessage.user_id, GroupMessage.sender_nickname).where(
                    GroupMessage.id_.in_([row.last_message_id for row in ranked])
                ),
            )
        ).all(),
    )
    return [nicknames.get(row.user_id) or f"用户-{str(row.user_id)[-4:]}" for row in ranked]


async def get_recent_speakers(
    group_id: str,
    hours: int = RECENT_SPEAKER_HOURS,
    limit: int = RECENT_SPEAKER_LIMIT,
    session: Optional["AsyncSession"] = None,
) -> list[str]:
    """获取最近 hours 小时内发言条数最多的前 limit 位成员昵称

    昵称取该成员最近一条消息记录里的 ``sender_nickname``；没有可用数据（或
    message_summary 插件未加载）时返回空列表。
    """
    group_message_model = _load_group_message_model()
    if group_message_model is None:
        return []
    if session is not None:
        return await _query_recent_speakers(session, group_message_model, group_id, hours, limit)
    async with get_session() as db_session:
        return await _query_recent_speakers(db_session, group_message_model, group_id, hours, limit)


async def _query_master_present(
    session: "AsyncSession",
    group_message_model: type,
    group_id: str,
    master_user_id: str,
) -> bool:
    """判定主人是否在本群的 Message Summary 记录中出现过，命中时写入 ChatGroup"""
    GroupMessage = group_message_model
    group = await session.get(ChatGroup, {"group_id": group_id})
    if group is not None and group.master_present:
        return True

    appeared = (
        await session.scalar(
            select(GroupMessage.id_)
            .where(GroupMessage.group_id == group_id)
            .where(or_(GroupMessage.user_id == master_user_id, GroupMessage.sender_nickname == master_user_id))
            .limit(1),
        )
    ) is not None
    if not appeared:
        return False
    if group is not None:
        group.master_present = True
        await session.commit()
        logger.info(f"[session_metadata] 群 {group_id} 首次观察到主人，已记录 master_present")
    # 没有群配置记录时不新建（enabled 没有默认值），本次仍按「出现过」返回
    return True


async def is_master_present(group_id: str, session: Optional["AsyncSession"] = None) -> bool:
    """主人是否在当前群聊出现过

    先在 ``ChatGroup.master_present`` 里查历史判定结果，没有再回查 Message Summary
    记录；命中后写入数据库且只增不减。``config.chat_master_user_id`` 为空时恒为
    False（不生成该指示由调用方负责）。
    """
    master_user_id = config.chat_master_user_id.strip()
    if not master_user_id:
        return False
    group_message_model = _load_group_message_model()
    if group_message_model is None:
        return False
    if session is not None:
        return await _query_master_present(session, group_message_model, group_id, master_user_id)
    async with get_session() as db_session:
        return await _query_master_present(db_session, group_message_model, group_id, master_user_id)


async def build_group_session_metadata(
    group_id: str,
    session: Optional["AsyncSession"] = None,
) -> list[str]:
    """构建群聊会话元数据行（最近发言者 + 主人是否在当前会话）

    只应在群聊会话中调用；任何查询失败都退化为不输出对应信息，不影响会话创建。
    """
    lines: list[str] = []
    if _load_group_message_model() is None:
        # 没有 Message Summary 数据时两项信息都无从判断，直接不输出
        return lines
    try:
        speakers = await get_recent_speakers(group_id, session=session)
        if speakers:
            lines.append("当前会话成员/最近发言者：" + "、".join(speakers) + "……")
        if config.chat_master_user_id.strip():
            present = await is_master_present(group_id, session=session)
            lines.append(f"{MASTER_DISPLAY_NAME} 是否在当前会话：{'是' if present else '否'}")
    except Exception as e:
        logger.debug(f"[session_metadata] 生成群聊会话元数据失败: {e}")
        return lines
    return lines
