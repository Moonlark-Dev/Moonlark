from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from nonebot_plugin_larklang.__main__ import LangHelper
from ..registry import ITEMS
from .properties import ItemProperties, get_properties

if TYPE_CHECKING:
    from .stack import ItemStack


class Item(ABC):

    properties: ItemProperties
    lang: LangHelper

    # 该物品的使用指令（不含指令前缀）；None 表示没有使用指令。
    # 由 /bag usage 展示，QQ 平台上会为该指令生成可点击按钮。
    usage_command: str | None = None

    def __init__(self, properties: ItemProperties = get_properties()):
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

    async def getDefaultName(self, stack: "ItemStack") -> str:
        key = f"{self.getLocation().getPath()}.description"
        user_id = stack.user_id
        if await self.lang.is_key_exists(key, user_id):
            return await self.getText(key, user_id)
        return await LangHelper("nonebot_plugin_item").text("name.none", user_id)

    async def getText(self, key: str, user_id: str, *args, **kwargs) -> str:
        """获取 LarkLang I18N 文本

        Args:
            key (str): 键名，不包含插件层
            user_id (str): 用户 ID

        Returns:
            str: 已被本地化的文本
        """
        return await self.lang.text(key, user_id, *args, **kwargs)

    async def getDefaultDescription(self, user_id: str) -> str:
        key = f"{self.getLocation().getPath()}.description"
        if await self.lang.is_key_exists(key, user_id):
            return await self.getText(key, user_id)
        return await LangHelper("nonebot_plugin_item").text("description.none", user_id)

    async def getUsageDescription(self, stack: "ItemStack") -> str | None:
        """获取物品的使用说明（本地化键 `<id>.usage`），未提供时返回 None"""
        key = f"{self.getLocation().getPath()}.usage"
        if not await self.lang.is_key_exists(key, stack.user_id):
            return None
        return await self.getText(key, stack.user_id)

    async def getDescription(self, stack: "ItemStack") -> str:
        return await self.getDefaultDescription(stack.user_id)
