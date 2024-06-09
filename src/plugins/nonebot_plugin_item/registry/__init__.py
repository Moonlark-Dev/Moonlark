from typing import TYPE_CHECKING
from .tags import ItemTags
from .registry import ResourceLocation

if TYPE_CHECKING:
    from ..base.item import Item

ITEMS: registry.Registry["Item"] = registry.Registry()
