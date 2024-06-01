from typing import TypedDict

from .models import ImageData


class ImageWithData(TypedDict):
    image: bytes
    data: ImageData
