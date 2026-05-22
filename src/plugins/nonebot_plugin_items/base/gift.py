from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from nonebot_plugin_larkuser import get_user
from nonebot import logger


from nonebot_plugin_chat.core.session import (
    create_private_session,
    get_session_directly,
    get_group_session_forced,
)
from nonebot_plugin_alconna import get_target

# 获取用户昵称（使用 larkuser 的 get_nickname）
from nonebot_plugin_larkuser import get_nickname

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

        自动处理好感度增加和 AI 回复。

        Args:
            stack: 物品堆叠
            bot: Bot 实例（从 kwargs 获取）
            event: Event 实例（从 kwargs 获取）
            group_id: 会话 ID（从 kwargs 获取）
            is_private: 是否为私聊场景（从 kwargs 获取）
            count: 实际使用数量（从 kwargs 获取，默认 1）

        Returns:
            使用结果
        """
        # 1. 增加好感度（使用实际数量而非 stack.count）
        user = await get_user(stack.user_id)
        count = kwargs.get("count", 1)
        total_fav = self.fav_value * count
        await user.add_fav(total_fav)
        logger.info(f"用户 {stack.user_id} 使用礼物 {self.getLocation()} x{count}, 好感度 +{total_fav}")

        # 2. 尝试触发 AI 回复
        bot = kwargs.get("bot")
        event = kwargs.get("event")
        group_id = kwargs.get("group_id")
        is_private = kwargs.get("is_private")

        if bot is not None and event is not None and group_id is not None and is_private is not None:
            await self._trigger_gift_response(stack, bot, event, group_id, is_private)

        # 3. 调用子类自定义逻辑
        return await self.on_gift_used(stack, **kwargs)

    async def _trigger_gift_response(
        self, stack: "ItemStack", bot: Any, event: Any, group_id: str, is_private: bool
    ) -> None:
        """
        触发礼物回复

        根据 is_private 判断场景，获取或创建对应 chat session，然后触发 AI 回复。

        Args:
            stack: 物品堆叠
            bot: Bot 实例
            event: Event 实例
            group_id: 会话 ID（私聊和群聊均由调用方传入 get_group_id()）
            is_private: 是否为私聊场景
        """
        try:
            # group_id 在私聊和群聊中都是正确的 session key
            try:
                session = get_session_directly(group_id)
            except KeyError:
                target = get_target(event)
                if is_private:
                    session = await create_private_session(group_id, target, bot)
                else:
                    session = await get_group_session_forced(group_id, target, bot)

            nickname = await get_nickname(stack.user_id, bot, event)

            gift_prompt = await self.getGiftPrompt(stack, nickname)

            # 触发 AI 回复
            await session.add_event(gift_prompt, trigger_mode="all")

        except Exception as e:
            logger.warning(f"触发礼物回复失败: {e}")

    @abstractmethod
    async def on_gift_used(self, stack: "ItemStack", **kwargs: Any) -> Any:
        """
        当礼物被使用时的回调

        子类应实现此方法以定义礼物使用的具体效果。

        Args:
            stack: 物品堆叠
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
            return await self.lang.text(
                "gift.prompt_with_description", stack.user_id, user_nickname, item_name, description
            )
        return await self.lang.text("gift.prompt", stack.user_id, user_nickname, item_name)
