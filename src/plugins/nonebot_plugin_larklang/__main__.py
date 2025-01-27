import inspect
import json
from typing import Optional
import random
from pathlib import Path
from types import ModuleType
from typing import NoReturn
from nonebot import get_driver, get_plugin_by_module_name, get_plugin_config, logger
from nonebot.matcher import Matcher
from nonebot_plugin_larkutils import parse_special_user_id
from .config import Config
from .exceptions import *
from .loader import LangLoader
from .models import LanguageData, LanguageKeyCache, DisplaySetting
from nonebot_plugin_orm import get_session, AsyncSession
from sqlalchemy import select
import copy


languages = {}
config = get_plugin_config(Config)
builtin_format = {"__prefix__": config.command_start[0]}


@get_driver().on_startup
async def load_languages() -> None:
    global languages
    async with get_session() as session:
        for item in await session.scalars(select(LanguageKeyCache)):
            await session.delete(item)
        await session.commit()
    loader = LangLoader(Path(config.language_dir), builtin_format)
    await loader.init()
    await loader.load()
    languages = copy.deepcopy(loader.get_languages())


def get_module_name(module: ModuleType | None) -> str | None:
    if module is None:
        return
    if (plugin := get_plugin_by_module_name(module.__name__)) is None:
        return
    return plugin.name[15:] if plugin.name.startswith("nonebot_plugin_") else plugin.name


def apply_template(language: str, plugin: str, key: str, text: str) -> str:
    try:
        return random.choice(languages[language].keys[plugin][key]["__template__"].text).format(text)
    except KeyError:
        return text


async def get_text(language: Optional[str], plugin: str, key: str, session: AsyncSession, *args, **kwargs) -> str:
    expr = select(LanguageKeyCache.text).where(LanguageKeyCache.plugin == plugin, LanguageKeyCache.key == key)
    if language is not None:
        expr = expr.where(LanguageKeyCache.language == language)
    data = (await session.scalars(expr)).first()
    if data is None:
        if language is not None:
            return await get_text(None, plugin, key, session, *args, **kwargs)
        else:
            return f"[缺失: {plugin}.{key} ({args}; {kwargs})]"
    text = random.choice(json.loads(data))
    try:
        return text.format(*args, **kwargs, **builtin_format)
    except IndexError:
        return text


def get_languages() -> dict[str, LanguageData]:
    return languages


async def set_user_language(user_id: str, language: str) -> None:
    async with get_session() as session:
        user = await session.get(DisplaySetting, user_id)
        if user is None:
            user = DisplaySetting(user_id=user_id, language=language)
        else:
            user.language = language
        await session.merge(user)
        await session.commit()


async def get_user_language(user_id: str, session: AsyncSession) -> str:
    if user_id.startswith("mlsid::") and "--lang" in (args := parse_special_user_id(user_id)):
        lang = args["--lang"]
        if lang == "default":
            lang = "zh_hans"
        return lang
    async with get_session() as session:
        user = await session.get(DisplaySetting, user_id)
        if user is not None:
            language = user.language
        else:
            language = "zh_hans"
    if language not in languages:
        await set_user_language(user_id, language := config.language_index_order[0])
    return language


class LangHelper:
    def __init__(self, name: str = "") -> None:
        module = inspect.getmodule(inspect.stack()[1][0])
        self.plugin_name = name or get_module_name(module) or ""
        if not self.plugin_name:
            raise InvalidPluginNameException(self.plugin_name)

    async def text(self, key: str, user_id: str | int, *args, **kwargs) -> str:
        session = get_session()
        language = await get_user_language(str(user_id), session)
        text = await get_text(language, self.plugin_name, key, session, *args, **kwargs)
        await session.close()
        return text

    async def is_key_exists(self, key: str, user_id: str | int) -> bool:
        return not (await self.text(key, user_id)).startswith("<缺失: ")

    async def send(
        self,
        key: str,
        user_id: str | int,
        *args,
        matcher: Matcher = Matcher(),
        at_sender: bool = True,
        reply_message: bool = False,
        **kwargs,
    ) -> None:
        await matcher.send(
            await self.text(key, user_id, *args, **kwargs), at_sender=at_sender, reply_message=reply_message
        )

    async def finish(
        self,
        key: str,
        user_id: str | int,
        *args,
        matcher: Matcher = Matcher(),
        at_sender: bool = True,
        reply_message: bool = False,
        **kwargs,
    ) -> NoReturn:
        await self.send(key, user_id, *args, **kwargs, at_sender=at_sender, reply_message=reply_message)
        await matcher.finish()

    async def reply(self, key: str, user_id: str | int, *args, **kwargs) -> None:
        await self.send(key, user_id, *args, **kwargs, at_sender=False, reply_message=True)
