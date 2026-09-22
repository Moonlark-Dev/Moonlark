from typing_extensions import TypedDict

from .models import ImageData


class ImageWithData(TypedDict):
    image: bytes
    data: ImageData
