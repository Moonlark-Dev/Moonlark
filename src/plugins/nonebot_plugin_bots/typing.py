from typing import TypedDict
from datetime import datetime


class SessionData(TypedDict):
    bot_id: str
    assign_time: datetime
