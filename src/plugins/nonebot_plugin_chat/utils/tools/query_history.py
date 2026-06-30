from sqlalchemy import select
from nonebot_plugin_orm import get_session
from nonebot_plugin_message_summary.models import GroupMessage

async def query_history_message(group_id: str, query: str) -> str:
    """查询当前会话的历史消息数据库"""
    async with get_session() as session:
        # 查询包含关键词的消息，按时间升序排列
        stmt = (
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.message.contains(query))
            .order_by(GroupMessage.id_)
        )
        results = await session.scalars(stmt)
        
        messages = []
        for msg in results:
            # 格式化每条消息: [时间] 发送者: 内容
            time_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"[{time_str}] {msg.sender_nickname}: {msg.message}")
        
        if not messages:
            return f"在历史消息中没有找到包含「{query}」的内容。"
        
        return "找到以下相关历史消息:\n" + "\n".join(messages)
