#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from typing import TYPE_CHECKING, Literal, Optional

from nonebot_plugin_openai.utils.functions import create_function_list
from nonebot_plugin_openai.utils.image_generation import generate_image
from nonebot_plugin_alconna import UniMessage
from ..enums import MoodEnum
from ..lang import lang
from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter, FunctionParameterWithEnum
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_bag.utils.item import get_bag_items
from nonebot_plugin_items.base.gift import GiftItem

from .tools import (
    browse_webpage,
    web_search,
    request_wolfram_alpha,
    search_abbreviation,
    describe_bilibili_video,
    resolve_b23_url,
    vm_create_task,
    vm_get_task_state,
    vm_send_input,
    vm_stop_task,
    is_vm_available,
)
from ..utils.emoji import QQ_EMOJI_MAP
from .note_manager import check_note, get_context_notes
from .status_manager import get_status_manager
from .instant_mem import get_memories_for_display

if TYPE_CHECKING:
    from ..core.processor import MessageProcessor


class ToolManager:
    def __init__(self, processor: Optional["MessageProcessor"] = None, lang_str: str = "zh_hans"):
        self.processor = processor
        self.lang_str = lang_str
        self.status_manager = get_status_manager()

    async def text(self, key: str, *args, **kwargs) -> str:
        if self.processor is not None:
            return await self.processor.session.text(key, *args, **kwargs)
        return await lang.text(key, self.lang_str, *args, **kwargs)

    async def browse_webpage(self, url: str) -> str:
        return await browse_webpage(url, self.text)

    async def web_search(self, keyword: str) -> str:
        return await web_search(keyword, self.text)

    async def search_abbreviation(self, text: str) -> str:
        return await search_abbreviation(text, self.text)

    async def describe_bilibili_video(self, bv_id: str) -> str:
        return await describe_bilibili_video(bv_id, self.text)

    async def resolve_b23_url(self, b23_url: str) -> str:
        return await resolve_b23_url(b23_url, self.text)

    async def vm_create_task(self, command: str, title: str) -> str:
        return await vm_create_task(command, title, self.text)

    async def vm_get_task_state(self, task_id: str) -> str:
        return await vm_get_task_state(task_id, self.text)

    async def vm_send_input(self, task_id: str, input_text: str) -> str:
        return await vm_send_input(task_id, input_text, self.text)

    async def vm_stop_task(self, task_id: str) -> str:
        return await vm_stop_task(task_id, self.text)

    async def set_mood(self, mood: str, reason: Optional[str] = None, intensity: float = 0.5) -> None:
        try:
            mood_enum = MoodEnum(mood)
        except ValueError:
            return

        self.status_manager.set_mood(mood_enum, reason, intensity)

    async def draw_image(self, prompt: str, size: str = "auto", quality: str = "high") -> str:
        """根据提示词生成图片并发送到当前会话"""
        if self.processor is None:
            raise RuntimeError("processor is None")

        image_bytes = await generate_image(prompt, size=size, quality=quality)

        message = UniMessage.image(raw=image_bytes)
        await message.send(target=self.processor.session.target, bot=self.processor.session.bot)

        return "图片已生成并发送"

    async def calculate_luck_value(self, nickname: str) -> str:
        """计算用户的人品值

        Args:
            nickname: 用户的昵称

        Returns:
            人品值结果消息
        """
        if self.processor is None:
            raise RuntimeError("processor is None")
        users = await self.processor.session.get_users()
        if not (user_id := users.get(nickname)):
            return await self.text("tools_desc.calculate_luck_value.user_not_found", nickname)
        luck_value = await get_luck_value(user_id)
        return await self.text("tools_desc.calculate_luck_value.result", nickname, luck_value)

    async def query_gift(self, target_nickname: str) -> str:
        """查询用户背包中可赠送给 Moonlark 的礼物及其数量

        Args:
            target_nickname: 要查询的用户的昵称

        Returns:
            格式化的礼物列表
        """
        if self.processor is None:
            raise RuntimeError("processor is None")

        # 获取用户列表 {nickname: user_id}
        users = await self.processor.session.get_users()
        if not (user_id := users.get(target_nickname)):
            return f"找不到用户「{target_nickname}」"

        # 获取用户背包物品
        try:
            items = await get_bag_items(user_id)
        except Exception as e:
            return f"查询背包失败: {e}"

        # 过滤出 GiftItem 并按名称合并数量
        gift_counts = {}
        for item in items:
            if isinstance(item.stack.item, GiftItem):
                name = await item.stack.getName()
                gift_counts[name] = gift_counts.get(name, 0) + item.stack.count

        if not gift_counts:
            return f"用户「{target_nickname}」背包中没有可送给 Moonlark 的礼物"

        # 格式化输出
        lines = [f"{name}：{count}" for name, count in sorted(gift_counts.items(), key=lambda x: -x[1])]
        return "\n".join(lines)

    async def change_sleep_status(
        self, deal_type: Literal["ready", "delay"], delay_minutes: Optional[int] = None, reason: Optional[str] = None
    ) -> str:
        """修改睡觉状态，委托给session处理"""
        if self.processor is None:
            raise RuntimeError("processor is None")
        return await self.processor.session.change_sleep_status(
            deal_type=deal_type, delay_minutes=delay_minutes, reason=reason
        )

    async def request_action(self, do: str, duration: Optional[int] = None) -> str:
        """向意识会话申请执行一个动作"""
        if self.processor is None:
            raise RuntimeError("processor is None")
        return await self.processor.session.request_action(do=do, duration=duration)

    async def request_sleep(self) -> str:
        """向意识会话申请睡觉"""
        if self.processor is None:
            raise RuntimeError("processor is None")
        return await self.processor.session.request_sleep()

    async def select_tools(self, mode: Literal["group", "agent"]) -> list[AsyncFunction]:
        tools = []
        emoji_id_table = None
        processor = self.processor

        # === 通用工具 ===

        # browse_webpage
        tools.append(self.browse_webpage)

        # web_search
        tools.append(self.web_search)

        # request_wolfram_alpha
        tools.append(request_wolfram_alpha)

        # search_abbreviation
        tools.append(self.search_abbreviation)

        # describe_bilibili_video
        tools.append(self.describe_bilibili_video)

        # resolve_b23_url
        tools.append(self.resolve_b23_url)

        # VM tools (如果可用)
        if mode == "agent" and is_vm_available():
            # vm_create_task
            tools.append(self.vm_create_task)

            # vm_get_task_state
            tools.append(self.vm_get_task_state)

            # vm_send_input
            tools.append(self.vm_send_input)

            # vm_stop_task
            tools.append(self.vm_stop_task)

        # # === Group 模式特有工具 ===
        if processor and mode == "group":
            # query_image
            tools.append(processor.query_image)
            tools.append(processor.send_message)

            # leave_for_a_while
            tools.append(processor.leave_for_a_while)

            # get_note_poster
            tools.append(self.push_note)

            # get_note_remover
            tools.append(self.remove_note)

            # set_timer
            tools.append(processor.session.set_timer)

            # sticker tools
            tools.append(processor.sticker_tools.save_sticker)
            tools.append(processor.sticker_tools.search_sticker)
            tools.append(processor.sticker_tools.recommend_sticker)
            tools.append(processor.sticker_tools.send_sticker)

            # ask_ai
            tools.append(processor.ai_agent.ask_ai)

            # refuse_interaction_request
            tools.append(self.deal_interaction_request)

            # draw_image
            tools.append(self.draw_image)

            # calculate_luck_value
            tools.append(self.calculate_luck_value)

            # query_gift
            tools.append(self.query_gift)

            # request_action
            tools.append(self.request_action)

            # change_sleep_status
            tools.append(self.change_sleep_status)

            # request_sleep
            tools.append(self.request_sleep)

            # query_history_message
            tools.append(self.query_history_message)

            # Conditional tools
            if processor and processor.session.is_napcat_bot():
                tools.append(processor.poke)
            if processor and processor.session.__class__.__name__ == "GroupSession":
                emoji_id_table = "/".join([f"{emoji}({emoji_id})" for emoji_id, emoji in QQ_EMOJI_MAP.items()])
                tools.append(processor.send_reaction)
            else:
                emoji_id_table = None

        return await create_function_list(tools, emoji_table=emoji_id_table)

    async def deal_interaction_request(self, interaction_id: str, deal_type: Literal["dodge", "bite", "enjoy"]) -> None:
        if self.processor is None:
            raise RuntimeError("processor is not set")
        if deal_type == "enjoy":
            await self.processor.accept_interaction_request(interaction_id)
        else:
            await self.processor.refuse_interaction_request(interaction_id, deal_type)

    async def remove_note(self, note_id: int) -> Optional[str]:
        # Get the note manager for this context

        if self.processor is None:
            raise RuntimeError("processor is None")
        note_manager = await get_context_notes(self.processor.session.session_id)
        # Try to delete the note
        success = await note_manager.delete_note(note_id)
        if not success:
            return await self.text("note.remove_not_found", note_id)

    async def push_note(
        self, text: str, expire_hours: Optional[float] = None, keywords: Optional[str] = None
    ) -> Optional[str]:
        # Get the note manager for this context
        if self.processor is None:
            raise RuntimeError("Session is None")
        note_manager = await get_context_notes(self.processor.session.session_id)
        note_check_result = await check_note(self.processor.session, keywords, text, expire_hours)
        if note_check_result["create"] == False:
            return await self.text("note.not_create", note_check_result["comment"])
        text = note_check_result["text"]
        keywords = note_check_result["keywords"]
        expire_hours = note_check_result["expire_hours"]
        await note_manager.create_note(content=text, keywords=keywords or "", expire_hours=expire_hours or 87600)

    async def query_history_message(self) -> str:
        from ..core.session import groups

        if self.processor is None:
            raise RuntimeError("processor is None")

        # 触发所有会话的即时记忆生成
        for group in groups.values():
            await group.processor.generate_instant_memory()

        result_parts = []

        # 展示非当前群聊的即时记忆
        current_session_id = self.processor.session.session_id
        memories = get_memories_for_display(current_session_id)
        if memories:
            mem_lines = []
            for mem in memories:
                mem_lines.append(
                    await self.text(
                        "prompt_group.instant_mem",
                        mem["create_time"].strftime("%Y-%m-%d %H:%M:%S"),
                        mem["expire_time"].strftime("%Y-%m-%d %H:%M:%S"),
                        mem["content"],
                    )
                )
            result_parts.append("即时记忆:\n" + "\n".join(mem_lines))
        else:
            result_parts.append("即时记忆: (无)")

        return "\n\n".join(result_parts)
