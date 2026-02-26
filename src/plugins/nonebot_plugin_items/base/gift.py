from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from nonebot_plugin_larkuser import get_user
from nonebot import logger


from nonebot_plugin_chat.core.session import (
    get_session_directly,
    get_group_session_forced,
    get_private_session,
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
            session_id: 会话 ID（从 kwargs 获取）
            is_private: 是否为私聊场景（从 kwargs 获取）

        Returns:
            使用结果
        """
        # 1. 增加好感度
        user = await get_user(stack.user_id)
        total_fav = self.fav_value * stack.count
        await user.add_fav(total_fav)
        logger.info(f"用户 {stack.user_id} 使用礼物 {self.getLocation()}, 好感度 +{total_fav}")

        # 2. 尝试触发 AI 回复
        bot = kwargs.get("bot")
        event = kwargs.get("event")
        session_id = kwargs.get("session_id")
        is_private = kwargs.get("is_private")

        if bot is not None and event is not None and session_id is not None and is_private is not None:
            await self._trigger_gift_response(stack, bot, event, session_id, is_private)

        # 3. 调用子类自定义逻辑
        return await self.on_gift_used(stack, *args, **kwargs)

    async def _trigger_gift_response(
        self, stack: "ItemStack", bot: Any, event: Any, session_id: str, is_private: bool
    ) -> None:
        """
        触发礼物回复

        根据 is_private 判断场景，获取或创建对应 chat session，然后触发 AI 回复。

        Args:
            stack: 物品堆叠
            bot: Bot 实例
            event: Event 实例
            session_id: 会话 ID（群聊为 group_id，私聊时需使用 user_id）
            is_private: 是否为私聊场景
        """
        try:

            # 根据 is_private 确定实际使用的 session_id
            if is_private:
                # 私聊场景：使用 user_id 作为 session_id
                actual_session_id = stack.user_id
            else:
                # 群聊场景：使用传入的 session_id（即 group_id）
                actual_session_id = session_id

            # 尝试获取已存在的 session
            try:
                session = get_session_directly(actual_session_id)
            except KeyError:
                # Session 不存在，需要创建
                target = get_target(event)
                if is_private:
                    # 私聊场景
                    session = await get_private_session(actual_session_id, target, bot)
                else:
                    # 群聊场景
                    session = await get_group_session_forced(actual_session_id, target, bot)


            nickname = await get_nickname(stack.user_id, bot, event)

            gift_prompt = await self.getGiftPrompt(stack, nickname)

            # 触发 AI 回复
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
            return await self.lang.text(
                "gift.prompt_with_description", stack.user_id, user_nickname, item_name, description
            )
        return await self.lang.text("gift.prompt", stack.user_id, user_nickname, item_name)
