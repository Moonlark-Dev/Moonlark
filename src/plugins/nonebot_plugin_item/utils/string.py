from .. import registry


def get_location_by_id(item_id: str) -> registry.ResourceLocation:
    namespace, path = item_id.split(":")
    for location, _ in registry.ITEMS.getEntries():
        if location.getNamespace() == namespace and location.getPath() == path:
            return location
    raise KeyError
