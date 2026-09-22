import tomllib
from typing import Any
from pathlib import Path
from nonebot_plugin_orm import get_session
import aiofiles
import yaml
from nonebot.compat import type_validate_python
from nonebot.log import logger
import json

from .models import LanguageData, LanguageKey, LanguageKeyCache


class KeysParser:

    def __init__(self, data: dict[str, dict], format_: Any):
        self.keys: dict[str, LanguageKey] = {}
        self.key = []
        self.parse(data)
        self.apply_templates(format_)

    def apply_templates(self, f: dict[str, Any]):
        templates = []
        for key, value in self.keys.items():
            name = key.split(".")[-1]
            if name == "__template__":
                templates.append(key[:-13])
        format_keys = {}
        for t in templates:
            for key, value in self.keys.items():
                if key.startswith(t) and value.use_template:
                    format_keys[key] = LanguageKey(
                        text=[self.keys[f"{t}.__template__"].text[0].format(v, **f) for v in value.text],
                        use_template=False,
                    )
        for key, value in format_keys.items():
            self.keys[key] = value
        for t in templates:
            self.keys.pop(f"{t}.__template__")

    def set_key(self, key: str, value: LanguageKey) -> None:
        string_key = ".".join(self.key + [key])
        self.keys[string_key] = value

    def parse(self, data: dict[str, Any]) -> None:
        for _key, value in data.items():
            key = str(_key)
            if isinstance(value, str):
                self.set_key(key, LanguageKey(text=[value]))
            elif isinstance(value, list):
                self.set_key(key, LanguageKey(text=value))
            elif isinstance(value, dict):
                if "text" in value:
                    if not isinstance(value["text"], list):
                        value["text"] = [str(value["text"])]
                    self.set_key(key, type_validate_python(LanguageKey, value))
                else:
                    self.key.append(key)
                    self.parse(value)
                    self.key.pop(-1)
            else:
                self.set_key(key, LanguageKey(text=[str(value)]))

    def get_keys(self) -> dict[str, LanguageKey]:
        return self.keys


class LangLoader:
    def __init__(self, base_path: Path, format_: Any) -> None:
        self.lang_list = [
            path for path in base_path.iterdir() if path.is_dir() and path.joinpath("language.toml").exists()
        ]
        logger.info(f"在 {base_path.as_posix()} 下找到 {len(self.lang_list)} 个语言")
        logger.debug(str(self.lang_list))
        self.languages: dict[str, LanguageData] = {}
        self.session = get_session()
        self.format = format_

    async def init(self) -> None:
        for lang in self.lang_list:
            await self.init_language(lang)
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
            await self.load_language(self.languages[lang].path)
        await self.session.commit()
        await self.session.close()

    async def load_language(self, lang: Path) -> None:
        for plugin in lang.iterdir():
            if not plugin.name.endswith(".yaml"):
                continue
            async with aiofiles.open(plugin, encoding="utf-8") as f:
                keys = KeysParser(yaml.safe_load(await f.read()), self.format).get_keys()
            await self.commit_keys(lang.name, plugin.name[:-5], keys)

    async def commit_keys(self, langugage: str, plugin: str, keys: dict[str, LanguageKey]) -> None:
        for key, value in keys.items():
            self.session.add(LanguageKeyCache(language=langugage, plugin=plugin, key=key, text=json.dumps(value.text)))

    def get_languages(self) -> dict[str, LanguageData]:
        return self.languages
