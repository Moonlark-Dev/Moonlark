from .. import registry


def get_location_by_id(item_id: str) -> registry.ResourceLocation:
    """
    Converts item ID to a ResourceLocation object.

    Parameters:
    item_id (str): The item ID in the format "namespace:path".

    Returns:
    registry.ResourceLocation: A ResourceLocation object representing the mod ID and item name.

    Raises:
    ValueError: If the item ID is not in the correct format.
    """
    namespace, path = item_id.split(":")

    # Return a ResourceLocation object
    return registry.ResourceLocation(namespace, path)