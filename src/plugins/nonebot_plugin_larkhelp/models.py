from pydantic import BaseModel


class CommandHelp(BaseModel):
    plugin: str
    description: str
    details: str
    usages: list[str]
    category: str = "main"


class CommandHelpData(BaseModel):
    plugin: str
    commands: dict[str, str | dict[str, str | list[str]]]
