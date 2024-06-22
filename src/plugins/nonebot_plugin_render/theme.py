import json
from pathlib import Path
import aiofiles
from nonebot_plugin_orm import get_session

from .models import ThemeConfig
from .config import config


async def get_themes() -> dict[str, str]:
    async with aiofiles.open(Path(__file__).parent.joinpath("themes.json"), encoding="utf-8") as f:
        return json.loads(await f.read())


async def get_user_theme(user_id: str) -> str:
    async with get_session() as session:
        user = await session.get(ThemeConfig, user_id)
        theme = user.theme if user else config.render_default_theme
    if theme not in await get_themes():
        theme = config.render_default_theme
    return theme


async def set_theme(user_id: str, theme: str) -> None:
    async with get_session() as session:
        user = await session.get(ThemeConfig, user_id)
        if user:
            user.theme = theme
        else:
            session.add(ThemeConfig(user_id=user_id, theme=theme))
        await session.commit()


async def get_theme_file(theme: str) -> str:
    return (await get_themes())[theme]
