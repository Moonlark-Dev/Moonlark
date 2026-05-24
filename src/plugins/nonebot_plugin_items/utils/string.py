from ..registry import ITEMS, ResourceLocation


def get_location_by_id(item_id: str) -> ResourceLocation:
    namespace, path = item_id.split(":")
    for location, _ in ITEMS.getEntries():
        if location.getNamespace() == namespace and location.getPath() == path:
            return location
    raise KeyError
