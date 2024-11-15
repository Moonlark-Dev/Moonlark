from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    language_dir: str = "src/lang"
    command_start: list[str] = ["/"]
