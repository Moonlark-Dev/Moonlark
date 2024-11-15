from nonebot_plugin_orm import get_session
import json
from pathlib import Path
import aiofiles
from nonebot_plugin_localstore import get_data_dir
from .config import config
from ..nonebot_plugin_larkutils import parse_special_user_id
from ..nonebot_plugin_larklang.models import DisplaySetting


async def get_themes() -> dict[str, str]:
    async with aiofiles.open(Path(__file__).parent.joinpath("themes.json"), encoding="utf-8") as f:
        return json.loads(await f.read())


async def get_user_theme(user_id: str) -> str:
    if user_id.startswith("mlsid::") and "--theme" in (args := parse_special_user_id(user_id)):
        return args["--theme"]
    async with get_session() as session:
        user = await session.get(DisplaySetting, user_id)
        if user is None:
            return config.render_default_theme
        theme = user.theme
    if theme not in await get_themes():
        theme = config.render_default_theme
    return theme

async def set_theme(user_id: str, theme: str) -> None:
    async with get_session() as session:
        user = await session.get(DisplaySetting, user_id)
        if user is None:
            user = DisplaySetting(
                user_id=user_id,
                theme=theme
            )
        else:
            user.theme=theme
        await session.merge(user)
        await session.commit()


async def get_theme_file(theme: str) -> str:
    return (await get_themes())[theme]
