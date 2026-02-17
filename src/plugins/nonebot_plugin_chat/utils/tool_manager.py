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
from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter, FunctionParameterWithEnum
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
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

if TYPE_CHECKING:
    from ..core.processor import MessageProcessor


class ToolManager:
    def __init__(self, processor: "MessageProcessor"):
        self.processor = processor

    async def text(self, key: str, *args, **kwargs) -> str:
        return await self.processor.session.text(key, *args, **kwargs)

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

    async def select_tools(self, mode: Literal["group", "agent"]) -> list[AsyncFunction]:
        tools = []
        processor = self.processor

        # === 通用工具 ===

        # browse_webpage
        tools.append(
            AsyncFunction(
                func=self.browse_webpage,
                description=await self.text("tools_desc.browse_webpage.desc"),
                parameters={
                    "url": FunctionParameter(
                        type="string",
                        description=await self.text("tools_desc.browse_webpage.url"),
                        required=True,
                    )
                },
            )
        )

        # web_search
        tools.append(
            AsyncFunction(
                func=self.web_search,
                description=await self.text("tools_desc.web_search.desc"),
                parameters={
                    "keyword": FunctionParameter(
                        type="string",
                        description=await self.text("tools_desc.web_search.keyword"),
                        required=True,
                    )
                },
            )
        )

        # request_wolfram_alpha
        tools.append(
            AsyncFunction(
                func=request_wolfram_alpha,
                description=await self.text("tools_desc.request_wolfram_alpha.desc"),
                parameters={
                    "question": FunctionParameter(
                        type="string",
                        description=await self.text("tools_desc.request_wolfram_alpha.question"),
                        required=True,
                    )
                },
            )
        )

        # search_abbreviation
        tools.append(
            AsyncFunction(
                func=self.search_abbreviation,
                description=await self.text("tools_desc.search_abbreviation.desc"),
                parameters={
                    "text": FunctionParameter(
                        type="string",
                        description=await self.text("tools_desc.search_abbreviation.text_arg"),
                        required=True,
                    )
                },
            )
        )

        # describe_bilibili_video
        tools.append(
            AsyncFunction(
                func=self.describe_bilibili_video,
                description=await self.text("tools_desc.describe_bilibili_video.desc"),
                parameters={
                    "bv_id": FunctionParameter(
                        type="string",
                        description=await self.text("tools_desc.describe_bilibili_video.bv_id"),
                        required=True,
                    )
                },
            )
        )

        # resolve_b23_url
        tools.append(
            AsyncFunction(
                func=self.resolve_b23_url,
                description=await self.text("tools_desc.resolve_b23_url.desc"),
                parameters={
                    "b23_url": FunctionParameter(
                        type="string",
                        description=await self.text("tools_desc.resolve_b23_url.b23_url"),
                        required=True,
                    )
                },
            )
        )

        # VM tools (如果可用)
        if mode == "agent" and is_vm_available():
            # vm_create_task
            tools.append(
                AsyncFunction(
                    func=self.vm_create_task,
                    description=await self.text("tools_desc.vm_create_task.desc"),
                    parameters={
                        "command": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.vm_create_task.command"),
                            required=True,
                        ),
                        "title": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.vm_create_task.title"),
                            required=True,
                        ),
                    },
                )
            )

            # vm_get_task_state
            tools.append(
                AsyncFunction(
                    func=self.vm_get_task_state,
                    description=await self.text("tools_desc.vm_get_task_state.desc"),
                    parameters={
                        "task_id": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.vm_get_task_state.task_id"),
                            required=True,
                        ),
                    },
                )
            )

            # vm_send_input
            tools.append(
                AsyncFunction(
                    func=self.vm_send_input,
                    description=await self.text("tools_desc.vm_send_input.desc"),
                    parameters={
                        "task_id": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.vm_send_input.task_id"),
                            required=True,
                        ),
                        "input_text": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.vm_send_input.input_text"),
                            required=True,
                        ),
                    },
                )
            )

            # vm_stop_task
            tools.append(
                AsyncFunction(
                    func=self.vm_stop_task,
                    description=await self.text("tools_desc.vm_stop_task.desc"),
                    parameters={
                        "task_id": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.vm_stop_task.task_id"),
                            required=True,
                        ),
                    },
                )
            )

        # === Group 模式特有工具 ===
        if mode == "group":

            # query_image
            tools.append(
                AsyncFunction(
                    func=processor.query_image,
                    description=await self.text("tools_desc.query_image.desc"),
                    parameters={
                        "image_id": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.query_image.image_id"),
                            required=True,
                        ),
                        "query_prompt": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.query_image.query_prompt"),
                            required=True,
                        ),
                    },
                )
            )

            # send_message
            tools.append(
                AsyncFunction(
                    func=processor.send_message,
                    description=await self.text("tools_desc.send_message.desc"),
                    parameters={
                        "message_content": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.send_message.message_content"),
                            required=True,
                        ),
                        "reply_message_id": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.send_message.reply_message_id"),
                            required=False,
                        ),
                    },
                )
            )

            # leave_for_a_while
            tools.insert(
                2,
                AsyncFunction(
                    func=processor.leave_for_a_while,
                    description=await self.text("tools_desc.leave_for_a_while.desc"),
                    parameters={},
                ),
            )

            # get_note_poster
            tools.append(
                AsyncFunction(
                    func=self.push_note,
                    description=await self.text("tools_desc.get_note_poster.desc"),
                    parameters={
                        "text": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.get_note_poster.text_arg"),
                            required=True,
                        ),
                        "expire_days": FunctionParameter(
                            type="integer",
                            description=await self.text("tools_desc.get_note_poster.expire_days"),
                            required=False,
                        ),
                        "keywords": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.get_note_poster.keywords"),
                            required=False,
                        ),
                        "expire_days": FunctionParameter(
                            type="integer",
                            description=await self.text("tools_desc.get_note_poster.expire_days"),
                            required=False,
                        ),
                        "keywords": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.get_note_poster.keywords"),
                            required=False,
                        ),
                    },
                )
            )

            # get_note_remover
            tools.append(
                AsyncFunction(
                    func=self.remove_note,
                    description=await self.text("tools_desc.get_note_remover.desc"),
                    parameters={
                        "note_id": FunctionParameter(
                            type="integer",
                            description=await self.text("tools_desc.get_note_remover.note_id"),
                            required=True,
                        ),
                    },
                )
            )

            # set_timer
            tools.append(
                AsyncFunction(
                    func=processor.session.set_timer,
                    description=await self.text("tools_desc.set_timer.desc"),
                    parameters={
                        "delay": FunctionParameter(
                            type="integer",
                            description=await self.text("tools_desc.set_timer.delay"),
                            required=True,
                        ),
                        "description": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.set_timer.description"),
                            required=True,
                        ),
                    },
                )
            )

            # sticker tools
            tools.append(
                AsyncFunction(
                    func=processor.sticker_tools.save_sticker,
                    description=await self.text("tools_desc.save_sticker.desc"),
                    parameters={
                        "image_id": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.save_sticker.image_id"),
                            required=True,
                        ),
                    },
                )
            )
            tools.append(
                AsyncFunction(
                    func=processor.sticker_tools.search_sticker,
                    description=await self.text("tools_desc.search_sticker.desc"),
                    parameters={
                        "query": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.search_sticker.query"),
                            required=True,
                        ),
                    },
                )
            )
            tools.append(
                AsyncFunction(
                    func=processor.sticker_tools.send_sticker,
                    description=await self.text("tools_desc.send_sticker.desc"),
                    parameters={
                        "sticker_id": FunctionParameter(
                            type="integer",
                            description=await self.text("tools_desc.send_sticker.sticker_id"),
                            required=True,
                        ),
                    },
                )
            )

            # ask_ai
            tools.append(
                AsyncFunction(
                    func=processor.ai_agent.ask_ai,
                    description=await self.text("tools_desc.ask_ai.desc"),
                    parameters={
                        "query": FunctionParameter(
                            type="string",
                            required=True,
                            description=await self.text("tools_desc.ask_ai.query"),
                        ),
                    },
                )
            )

            # refuse_interaction_request
            tools.append(
                AsyncFunction(
                    func=processor.refuse_interaction_request,
                    description=await self.text("tools_desc.refuse_interaction_request.desc"),
                    parameters={
                        "id_": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.refuse_interaction_request.id_"),
                            required=True,
                        ),
                        "type_": FunctionParameterWithEnum(
                            type="string",
                            description=await self.text("tools_desc.refuse_interaction_request.type_"),
                            required=True,
                            enum={"dodge", "bite"},
                        ),
                    },
                )
            )

            # judge_user_behavior
            tools.append(
                AsyncFunction(
                    func=processor.judge_user_behavior,
                    description=await self.text("tools_desc.judge_user_behavior.desc"),
                    parameters={
                        "nickname": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.judge_user_behavior.nickname"),
                            required=True,
                        ),
                        "score": FunctionParameter(
                            type="integer",
                            description=await self.text("tools_desc.judge_user_behavior.score"),
                            required=True,
                        ),
                        "reason": FunctionParameter(
                            type="string",
                            description=await self.text("tools_desc.judge_user_behavior.reason"),
                            required=True,
                        ),
                    },
                )
            )

            # Conditional tools
            if processor.session.is_napcat_bot():
                tools.append(
                    AsyncFunction(
                        func=processor.poke,
                        description=await self.text("tools_desc.poke.desc"),
                        parameters={
                            "target_name": FunctionParameter(
                                type="string",
                                description=await self.text("tools_desc.poke.target_name"),
                                required=True,
                            ),
                        },
                    )
                )

            if isinstance(processor.session.bot, OB11Bot):
                tools.append(
                    AsyncFunction(
                        func=processor.delete_message,
                        description=await self.text("tools_desc.delete_message.desc"),
                        parameters={
                            "message_id": FunctionParameter(
                                type="integer",
                                description=await self.text("tools_desc.delete_message.message_id"),
                                required=True,
                            )
                        },
                    )
                )

            # GroupSession specific tools
            # Note: We check if session has adapter_group_id to imply GroupSession or import GroupSession to check instance
            # Avoiding circular import, checking attribute existence or class name might be safer if types not imported
            # But GroupSession inherits from BaseSession.
            # Let's check if session has attribute 'group_users' which implies group context, or just check class name
            if processor.session.__class__.__name__ == "GroupSession":
                emoji_id_table = ", ".join([f"{emoji}({emoji_id})" for emoji_id, emoji in QQ_EMOJI_MAP.items()])
                tools.append(
                    AsyncFunction(
                        func=processor.send_reaction,
                        description=await self.text("tools_desc.send_reaction.desc", emoji_id_table),
                        parameters={
                            "message_id": FunctionParameter(
                                type="string",
                                description=await self.text("tools_desc.send_reaction.message_id"),
                                required=True,
                            ),
                            "emoji_id": FunctionParameterWithEnum(
                                type="string",
                                description=await self.text("tools_desc.send_reaction.emoji_id"),
                                required=True,
                                enum=set(QQ_EMOJI_MAP.keys()),
                            ),
                        },
                    )
                )

        return tools

    async def remove_note(self, note_id: int) -> str:
        # Get the note manager for this context
        note_manager = await get_context_notes(self.processor.session.session_id)
        # Try to delete the note
        success = await note_manager.delete_note(note_id)
        if success:
            return await self.text("note.remove_success", note_id)
        else:
            return await self.text("note.remove_not_found", note_id)

    async def push_note(self, text: str, expire_days: Optional[int] = None, keywords: Optional[str] = None) -> str:
        # Get the note manager for this context
        note_manager = await get_context_notes(self.processor.session.session_id)
        note_check_result = await check_note(self.processor.session, keywords, text, expire_days)
        if note_check_result["create"] == False:
            return await self.text("note.not_create", note_check_result["comment"])
        text = note_check_result["text"]
        keywords = note_check_result["keywords"]
        expire_days = note_check_result["expire_days"]
        await note_manager.create_note(content=text, keywords=keywords or "", expire_days=expire_days or 3650)
        return await self.text("note.create")
