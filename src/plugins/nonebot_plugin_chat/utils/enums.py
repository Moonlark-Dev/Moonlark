from enum import Enum, auto


class FetchStatus(Enum):
    SUCCESS = auto()
    FAILED = auto()
    SKIP = auto()
