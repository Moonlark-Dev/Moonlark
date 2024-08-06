from pathlib import Path
from pydantic import BaseModel


class LanguageLockData(BaseModel):
    enable: bool = False
    price: int = 0


class LanguageDisplayData(BaseModel):
    hidden: bool = False
    description: str = ""


class LanguagePatchData(BaseModel):
    patch: bool = False
    base: str = "zh_hans"


class LanguageKey(BaseModel):
    text: list[str]
    use_template: bool = True


class LanguageData(BaseModel):
    # 由 Moonlark 自动填入
    path: Path
    keys: dict[str, dict[str, dict[str, LanguageKey]]] = {}
    # Language 节
    author: str = "Unknown"
    version: str = "latest"
    # 其他节
    lock: LanguageLockData = LanguageLockData()
    display: LanguageDisplayData = LanguageDisplayData()
    patch: LanguagePatchData = LanguagePatchData()

