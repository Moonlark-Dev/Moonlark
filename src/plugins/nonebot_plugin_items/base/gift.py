from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from .useable import UseableItem
from .properties import ItemProperties, get_properties

if TYPE_CHECKING:
    from .stack import ItemStack


class GiftItem(UseableItem, ABC):
    """
    礼物物品基类

    继承此类的物品可以作为礼物赠送给机器人，会触发好感度增加和 AI 回复。
    """

    # 基础好感度增加值
    fav_value: float = 0.005

    def __init__(self, properties: ItemProperties = get_properties()):
        super().__init__(properties)

    async def useItem(self, stack: "ItemStack", *args: Any, **kwargs: Any) -> Any:
        """
        使用礼物物品

        子类可以覆盖此方法以实现自定义逻辑，但需要调用 super().useItem() 来触发礼物处理。

        Args:
            stack: 物品堆叠
            session: Chat 会话对象（可选，由 GiftManager 使用）

        Returns:
            使用结果
        """
        # 获取 session 参数（如果提供）
        session = kwargs.get("session")

        if session is not None:
            # 导入 GiftManager 处理礼物
            from nonebot_plugin_chat.utils.gift_manager import get_gift_manager

            gift_manager = get_gift_manager()
            await gift_manager.handle_gift(stack, session)

        return await self.on_gift_used(stack, *args, **kwargs)

    @abstractmethod
    async def on_gift_used(self, stack: "ItemStack", *args: Any, **kwargs: Any) -> Any:
        """
        当礼物被使用时的回调

        子类应实现此方法以定义礼物使用的具体效果。

        Args:
            stack: 物品堆叠
            *args: 额外位置参数
            **kwargs: 额外关键字参数

        Returns:
            使用结果
        """
        ...

    async def getGiftPrompt(self, stack: "ItemStack", user_nickname: str) -> str:
        """
        获取礼物事件的提示文本

        用于生成 AI 回复的上下文。

        Args:
            stack: 物品堆叠
            user_nickname: 赠送者的昵称

        Returns:
            礼物事件描述文本
        """
        item_name = await self.getName(stack)
        description = await self.getDescription(stack)

        if description:
            return f"{user_nickname} 送给你 {item_name}：{description}"
        return f"{user_nickname} 送给你 {item_name}"
