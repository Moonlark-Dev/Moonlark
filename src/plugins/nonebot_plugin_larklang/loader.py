import tomllib
import traceback
from pathlib import Path

import aiofiles
import yaml
from nonebot.compat import type_validate_python
from nonebot.log import logger

from .models import LanguageData, LanguageKey


def init_keys(data: dict[str, dict]) -> None:
    # NOTE 有点乱，待优化
    for cmd in data.keys():
        keys = data[cmd].keys()
        for key in keys:
            if isinstance(data[cmd][key], str):
                data[cmd][key] = LanguageKey(text=[data[cmd][key]])
            elif isinstance(data[cmd][key], list):
                data[cmd][key] = LanguageKey(text=data[cmd][key])
            elif isinstance(data[cmd][key], dict):
                if isinstance(data[cmd][key]["text"], str):
                    data[cmd][key]["text"] = [data[cmd][key]["text"]]
                data[cmd][key] = type_validate_python(LanguageKey, data[cmd][key])
            else:
                data[cmd].pop(key)


class LangLoader:
    def __init__(self, base_path: Path) -> None:
        self.lang_list = [
            path for path in base_path.iterdir() if path.is_dir() and path.joinpath("language.toml").exists()
        ]
        logger.info(f"在 {base_path.as_posix()} 下找到 {len(self.lang_list)} 个语言")
        logger.debug(str(self.lang_list))
        self.languages: dict[str, LanguageData] = {}

    async def init(self) -> None:
        for lang in self.lang_list:
            try:
                await self.init_language(lang)
            except Exception:
                logger.warning(f"初始化语言 {lang.name} 失败: {traceback.format_exc()}")
        logger.debug(str(self.languages))
        del self.lang_list

    async def init_language(self, lang: Path) -> None:
        async with aiofiles.open(lang.joinpath("language.toml"), encoding="utf-8") as f:
            data = tomllib.loads(await f.read())
            data["path"] = lang
            # 拉平 language 字段
            data.update(data.pop("language"))
            self.languages[lang.name] = type_validate_python(LanguageData, data)

    async def load(self) -> None:
        lang_list = list(self.languages.keys())
        for lang in lang_list:
            try:
                await self.load_language(self.languages[lang].path)
            except Exception:
                logger.warning(f"加载语言 {lang} 失败: {traceback.format_exc()}")
                self.languages.pop(lang)

    async def load_language(self, lang: Path) -> None:
        for plugin in lang.iterdir():
            if not plugin.name.endswith(".yaml"):
                continue
            async with aiofiles.open(plugin, encoding="utf-8") as f:
                self.languages[lang.name].keys[plugin.name[:-5]] = yaml.safe_load(await f.read())
                init_keys(self.languages[lang.name].keys[plugin.name[:-5]])

    def get_languages(self) -> dict[str, LanguageData]:
        return self.languages
