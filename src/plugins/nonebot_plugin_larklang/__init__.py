from types import ModuleType
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larklang",
    description="Moonlark 本地化插件",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

from .loader import LangLoader
from pathlib import Path
from .model import LanguageData
from nonebot import get_driver
import random
import inspect
from nonebot import get_plugin_by_module_name
from .exception import *

languages = {}

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

def get_text(language: str, plugin: str, key: str, *format_) -> str:
    k = key.split(".", 1)
    try:
        data = languages[language].keys[plugin][k[0]][k[1]]
    except KeyError:
        text = f"<缺失: {plugin}.{key}; {format_}>"
    else:
        text = random.choice(data.text)
        if data.use_template and "__template__" in languages[language].keys[plugin][k[0]]:
            text = get_text(language, plugin, f"{k[0]}.__template__", text)
    return text.format(*format_)


class LangHelper:

    def __init__(self, name: str = "") -> None:
        module = inspect.getmodule(inspect.stack()[1][0])
        self.plugin_name = name or get_module_name(module)
        if not self.plugin_name:
            raise InvalidPluginNameException(self.plugin_name)


