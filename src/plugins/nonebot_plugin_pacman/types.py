from typing import Literal, TypedDict


class PackageData(TypedDict):
    name: str
    arch: Literal["x86_64", "any"]
    description: str
    last_update: str
    license: str
    size: str
    out_of_date: bool
    version: str
    repo: str
