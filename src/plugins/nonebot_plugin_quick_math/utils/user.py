import copy
from datetime import datetime
from nonebot_plugin_orm import get_session

from ..models import QuickMathUser


async def update_user_data(user_id: str, point: int) -> tuple[int, int]:
    async with get_session() as session:
        data = await session.get(QuickMathUser, user_id)
        if data is not None:
            data.total_point += point
            record = copy.deepcopy(data.max_point)
            if point > data.max_point:
                data.max_point = point
            data.last_use = datetime.now()
            await session.commit()
            return point - record, record
        else:
            session.add(QuickMathUser(user_id=user_id, max_point=point, total_point=point, last_use=datetime.now()))
            await session.commit()
            return point, 0
