from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ...nonebot_plugin_larklang.__main__ import LangHelper
from ..registry import ITEMS
from .properties import ItemProperties, default

if TYPE_CHECKING:
    from .stack import ItemStack


class Item(ABC):

    properties: ItemProperties
    lang: LangHelper

    def __init__(self, properties: ItemProperties = default()):
        self.properties = properties
        self.setupLang()

    def getProperties(self) -> ItemProperties:
        return self.properties

    @abstractmethod
    def setupLang(self) -> None: ...

    def getLocation(self):
        return ITEMS.getKey(self)

    async def getName(self, stack: "ItemStack") -> str:
        if "custom_name" in stack.data:
            return stack.data["custom_name"]
        return await self.getDefaultName(stack)

    @abstractmethod
    async def getDefaultName(self, stack: "ItemStack") -> str: ...

    async def getText(self, key: str, user_id: str, *args, **kwargs) -> str:
        """获取 LarkLang I18N 文本

        Args:
            key (str): 键名，不包含插件层
            user_id (str): 用户 ID

        Returns:
            str: 已被本地化的文本
        """
        return await self.lang.text(key, user_id, *args, **kwargs)

    def isUseable(self, stack: "ItemStack") -> bool:
        if "useable" in stack.data:
            return stack.data["useable"]
        else:
            return self.properties["useable"]
