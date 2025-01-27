from typing import TypedDict, Literal, overload


class ItemProperties(TypedDict):
    useable: bool
    star: Literal[1, 2, 3, 4, 5]
    max_stack: int
    multi_use: bool


def get_properties(
    useable: bool = False,
    star: Literal[1, 2, 3, 4, 5] = 2,
    max_stack: int = 64,
    multi_use: bool = False,
) -> ItemProperties:
    return {"useable": useable, "star": star, "max_stack": max_stack, "multi_use": multi_use}
