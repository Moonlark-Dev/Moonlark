from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    language_dir: str = "src/plugins"
    language_index_order: list[str] = ["zh_hans"]
