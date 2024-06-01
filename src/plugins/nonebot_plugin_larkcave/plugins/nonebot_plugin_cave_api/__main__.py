import base64
from nonebot import get_app
from .types import RandomCaveResponse
from ...__main__ import get_cave
from nonebot_plugin_orm import get_scoped_session
from ....nonebot_plugin_larkuser import get_user
from ...models import ImageData
from sqlalchemy import select

app = get_app()

@app.get("/api/get_cave")
async def _() -> RandomCaveResponse:
    session = get_scoped_session()
    cave = await get_cave(session)
    return {
        "id": cave.id,
        "content": cave.content,
        "time": cave.time.timestamp(),
        "author": (await get_user(cave.author)).nickname,
        "images": [
            {
                "id": image.id,
                "name": image.name,
                "data": base64.b64encode(image.data).decode()
            } for image in (await session.scalars(select(ImageData).where(ImageData.belong == cave.id))).all()
        ]
    }