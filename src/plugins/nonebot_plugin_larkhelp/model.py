from pydantic import BaseModel

class CommandHelp(BaseModel):
    plugin: str
    description: str
    information: str
    usages: list[str]

class CommandHelpData(BaseModel):
    plugin: str
    commands: dict
