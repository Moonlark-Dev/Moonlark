from typing import TYPE_CHECKING
from .tags import ItemTags
from .registry import ResourceLocation, Registry

if TYPE_CHECKING:
    from ..base.item import Item

ITEMS: Registry["Item"] = Registry()
