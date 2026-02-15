from enum import Enum, auto


class FetchStatus(Enum):
    SUCCESS = auto()
    WRONG_TOOL_CALL = auto()
    FAILED = auto()
    EMPTY_REPLY = auto()
    NO_MESSAGE_SENT = auto()
