from typing_extensions import TypedDict


class Image(TypedDict):
    id: float
    data: str
    name: str


class RandomCaveResponse(TypedDict):
    id: int
    content: str
    author: str
    time: float
    images: list[Image]
