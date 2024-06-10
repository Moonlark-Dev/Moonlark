from typing import TypedDict, Literal


class ItemProperties(TypedDict):
    useable: bool
    star: Literal[1, 2, 3, 4, 5]
    max_stack: int


def default() -> ItemProperties:
    properties: ItemProperties = {
        'useable': False,
        'star': 2,
        'max_stack': 64
    }
    return properties
