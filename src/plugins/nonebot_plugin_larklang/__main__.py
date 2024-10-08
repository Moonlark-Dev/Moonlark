import inspect
import aiofiles
import random
import traceback
from pathlib import Path
from types import ModuleType

from typing import NoReturn
from nonebot import get_driver, get_plugin_by_module_name, get_plugin_config, logger
from nonebot.matcher import Matcher
from nonebot_plugin_localstore import get_data_dir

from ..nonebot_plugin_larkutils import parse_special_user_id
from .config import Config
from .exceptions import *
from .loader import LangLoader
from .models import LanguageData

languages = {}
config = get_plugin_config(Config)
data_dir = get_data_dir("nonebot_plugin_larklang")


@get_driver().on_startup
async def load_languages() -> None:
    global languages
    loader = LangLoader(Path(config.language_dir))
    await loader.init()
    await loader.load()
    languages = loader.get_languages().copy()


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
        logger.waring(f"{traceback.format_exc()}")
        return text


def get_text(language: str, plugin: str, key: str, *args, retry: bool = True, **kwargs) -> str:
    k = key.split(".", 1)
    try:
        data = languages[language].keys[plugin][k[0]][k[1]]
    except KeyError:
        logger.warning(f"获取键失败: {traceback.format_exc()}")
        if retry:
            if language in languages and languages[language].patch.patch:
                return get_text(languages[language].patch.base, plugin, key, *args, retry=False, **kwargs)
            for lang in config.language_index_order:
                text = get_text(lang, plugin, key, *args, retry=False, **kwargs)
                if text.startswith("<缺失: ") and text.endswith(">"):
                    continue
                return text
        return f"<缺失: {plugin}.{key}; {args}; {kwargs}>"
    else:
        text = random.choice(data.text)
        if data.use_template:
            text = apply_template(language, plugin, k[0], text)
    logger.debug(f"GetTEXT: {plugin}.{key}; {args}; {kwargs}")
    try:
        return text.format(*args, **kwargs, __prefix__=config.command_start[0])
    except IndexError:
        logger.waring(f"{traceback.format_exc()}")
        return text


def get_languages() -> dict[str, LanguageData]:
    return languages


async def set_user_language(user_id: str, language: str) -> None:
    async with aiofiles.open(data_dir.joinpath(user_id), "w", encoding="utf-8") as f:
        await f.write(language)


async def get_user_language(user_id: str) -> str:
    if user_id.startswith("mlsid::") and "--lang" in (args := parse_special_user_id(user_id)):
        lang = args["--lang"]
        if lang == "default":
            lang = config.language_index_order[0]
        return lang
    file = data_dir.joinpath(user_id)
    if file.exists():
        async with aiofiles.open(file, "r", encoding="utf-8") as f:
            language = await f.read()
    else:
        language = config.language_index_order[0]
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
        language = await get_user_language(str(user_id))
        return get_text(language, self.plugin_name, key, *args, **kwargs)

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
