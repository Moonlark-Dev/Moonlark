from nonebot_plugin_orm import Model, async_scoped_session
from sqlalchemy import select
from sqlalchemy.sql import func
from sqlalchemy.sql._typing import ColumnExpressionArgument


async def get_id(session: async_scoped_session, col: ColumnExpressionArgument[int]) -> int:
    result = await session.scalar(select(func.max(col)))
    return (result + 1) if result is not None else 0
