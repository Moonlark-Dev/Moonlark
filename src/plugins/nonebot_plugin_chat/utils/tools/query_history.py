from sqlalchemy import select
from nonebot_plugin_orm import get_session
from nonebot_plugin_message_summary.models import GroupMessage


async def fetch_history_messages(group_id: str, limit: int = 1000) -> str:
    """拉取当前会话的最近历史消息数据库"""
    async with get_session() as session:
        # 拉取最近的 N 条消息，按 ID 降序排列
        stmt = (
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .order_by(GroupMessage.id_.desc())
            .limit(limit)
        )
        results = await session.scalars(stmt)

        # 将结果转换为列表并反转，使其按时间升序排列
        messages = list(results)
        messages.reverse()

        formatted = []
        for msg in messages:
            # 格式化每条消息: [时间] 发送者: 内容
            time_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            formatted.append(f"[{time_str}] {msg.sender_nickname}: {msg.message}")

        return "\n".join(formatted)
