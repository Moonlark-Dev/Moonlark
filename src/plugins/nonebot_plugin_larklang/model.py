from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from pathlib import Path
from nonebot_plugin_orm import Model

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
    encoding: str = "utf-8"
    # 其他节
    lock: LanguageLockData = LanguageLockData()
    display: LanguageDisplayData = LanguageDisplayData()
    patch: LanguagePatchData = LanguagePatchData()

class LanguageConfig(Model):
    user_id: Mapped[str] = mapped_column(primary_key=True)
    language: Mapped[str]
