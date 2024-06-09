from .tags import ItemTags
from .registry import ResourceLocation
from ..item import Item

ITEMS: registry.Registry[Item] = registry.Registry()

