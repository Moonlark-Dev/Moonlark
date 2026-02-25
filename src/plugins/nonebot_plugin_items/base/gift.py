from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from nonebot_plugin_larkuser import get_user
from nonebot import logger

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

        自动处理好感度增加。如果提供了 session 参数，还会触发 AI 回复。

        Args:
            stack: 物品堆叠
            session: Chat 会话对象（可选，用于触发 AI 回复）

        Returns:
            使用结果
        """
        # 1. 增加好感度（无论是否有 session 都执行）
        user = await get_user(stack.user_id)
        total_fav = self.fav_value * stack.count
        await user.add_fav(total_fav)
        logger.info(f"用户 {stack.user_id} 使用礼物 {self.getLocation()}, 好感度 +{total_fav}")

        # 2. 如果有 session，触发 AI 回复
        session = kwargs.get("session")
        if session is not None:
            await self._trigger_gift_response(stack, session)

        # 3. 调用子类自定义逻辑
        return await self.on_gift_used(stack, *args, **kwargs)

    async def _trigger_gift_response(self, stack: "ItemStack", session: Any) -> None:
        """
        触发礼物回复

        Args:
            stack: 物品堆叠
            session: Chat 会话对象
        """
        try:
            from nonebot_plugin_chat.utils.gift_manager import get_gift_manager

            gift_manager = get_gift_manager()
            nickname = await gift_manager._get_user_nickname(session, stack.user_id)
            gift_prompt = await self.getGiftPrompt(stack, nickname)
            await session.add_event(gift_prompt, trigger_mode="all")
        except Exception as e:
            logger.warning(f"触发礼物回复失败: {e}")

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
