from typing import TypedDict


class ItemProperties(TypedDict):
    useable: bool


def default() -> ItemProperties:
    properties: ItemProperties = {
        'useable': False
    }
    return properties
