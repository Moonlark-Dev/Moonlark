from typing import Optional
from pydantic import BaseModel



class CommandHelp(BaseModel):
    plugin: str
    description: str
    information: Optional[str] = None
    usages: list[str]

class CommandHelpData(BaseModel):
    plugin: str
    commands: dict
