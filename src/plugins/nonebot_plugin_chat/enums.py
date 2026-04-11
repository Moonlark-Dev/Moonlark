from enum import Enum, auto


class FetchStatus(Enum):
    SUCCESS = auto()
    FAILED = auto()
    SKIP = auto()


class MoodEnum(str, Enum):
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    CALM = "calm"
    BORED = "bored"
    CONFUSED = "confused"
    TIRED = "tired"
    SHY = "shy"


class StateEnum(Enum):
    SLEEPING = "sleeping"
    ACTIVATE = "activate"
    BORED = "bored"
    BUSY = "busy"
