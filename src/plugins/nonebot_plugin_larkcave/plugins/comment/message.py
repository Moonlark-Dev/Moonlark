from typing import Optional
from .types import CaveMessage
from .config import config

cave_messages: list[CaveMessage] = []


def get_cave_by_message_id(message_id: str) -> Optional[int]:
    for message in cave_messages:
        if message["message_id"] == message_id:
            return message["cave_id"]


def add_cave_message(cave_id: int, message_id: str) -> None:
    global cave_messages
    cave_messages.append({"cave_id": cave_id, "message_id": message_id})
    cave_messages = cave_messages[-config.cave_message_list_length :]
    # print(cave_messages)
