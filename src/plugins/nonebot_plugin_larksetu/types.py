from typing import TypedDict
from .model import ImageData

class ImageWithData(TypedDict):
    image: bytes
    data: ImageData