from typing import Awaitable, Callable, Optional
from nonebot.log import logger
from nonebot import get_driver, get_bots
import aiofiles
import hashlib
from nonebot_plugin_localstore import get_cache_dir
from nonebot_plugin_larklang.__main__ import get_languages
from .theme import get_themes
from .config import config


CACHE_CREATOR_TYPE = Callable[[str], Awaitable[bytes]]
creator_functions: dict[str, CACHE_CREATOR_TYPE] = {}
cache_dir = get_cache_dir("nonebot-plugin-render")


def creator(template_name: str):
    def d(func: CACHE_CREATOR_TYPE) -> CACHE_CREATOR_TYPE:
        creator_functions[template_name] = func
        return func

    return d


async def setup_cache() -> None:
    languages = get_languages().keys()
    themes = (await get_themes()).keys()
    for template, function in creator_functions.items():
        for lang in languages:
            for theme in themes:
                image = await function(f"mlsid::--lang={lang};--theme={theme}")
                f_name = hashlib.sha256(
                    f"mlrc::--template={template};--lang={lang};--theme={theme}".encode()
                ).hexdigest()
                async with aiofiles.open(cache_dir.joinpath(f_name), "wb") as f:
                    await f.write(image)
                logger.debug(f"成功为 {template=} {lang=} {theme=} 创建 Render 缓存！")
    logger.success("Render 缓存创建完成！")


@get_driver().on_bot_connect
async def _() -> None:
    for file in cache_dir.iterdir():
        if file.is_file():
            file.unlink()
    if config.render_cache and len(get_bots().keys()) <= 1:
        await setup_cache()


async def get_cache(template: str, lang: str, theme: str) -> Optional[bytes]:
    f_name = hashlib.sha256(f"mlrc::--template={template};--lang={lang};--theme={theme}".encode()).hexdigest()
    path = cache_dir.joinpath(f_name)
    if path.exists():
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
    return None
