import traceback
from typing import TYPE_CHECKING, Awaitable, Optional

from nonebot_plugin_chat.models import ModelResponse
from nonebot_plugin_chat.utils.emoji import QQ_EMOJI_MAP
from nonebot_plugin_chat.utils.tools.wolfram_alpha import request_wolfram_alpha
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message

if TYPE_CHECKING:
    from .processor import MessageProcessor


class ToolExecutor:
    def __init__(self, processor: "MessageProcessor", fetcher: MessageFetcher, analysis: ModelResponse):
        self.processor = processor
        self.analysis = analysis
        self.fetcher = fetcher

    def append_response(self, response: str) -> None:
        self.fetcher.session.insert_message(generate_message(response, "user"))

    async def append_error(self, tool_name: str, error: str) -> None:
        self.fetcher.session.insert_message(
            generate_message(await self.processor.session.text("tool_executor.error", tool_name, error), "user")
        )

    async def _execute(self, func: Awaitable[Optional[str]], tool_name: str) -> None:
        try:
            response = await func
            if response:
                self.append_response(response)
        except Exception as e:
            await self.append_error(tool_name, traceback.format_exc())

    async def get_sticker_recommend(self) -> str:
        return "\n".join([i async for i in self.processor.generate_sticker_recommendations()])

    async def _describe_bilibili_video(self, bv_or_b23_url: str) -> str:
        if "b23.tv" in bv_or_b23_url:
            bv_id = await self.processor.tool_manager.resolve_b23_url(bv_or_b23_url)
        else:
            bv_id = bv_or_b23_url
        return await self.processor.tool_manager.describe_bilibili_video(bv_id)

    async def send_reaction(self, message_id: str, reaction: str) -> Optional[str]:
        try:
            emoji_id = [key for key, value in QQ_EMOJI_MAP.items() if value == reaction][0]
        except IndexError:
            return await self.processor.session.text("tools.reaction_not_found")
        await self.processor.send_reaction(message_id, emoji_id)

    async def execute(self) -> None:
        analysis = self.analysis
        tool_manager = self.processor.tool_manager
        if analysis.leave_for_a_while:
            await self.processor.session.mute()
        if target_name := analysis.poke:
            await self._execute(self.processor.poke(target_name), "poke")
        if note_id := analysis.remove_note:
            await self._execute(tool_manager.remove_note(note_id), "remove_note")
        if query := analysis.search_sticker:
            await self._execute(self.processor.sticker_tools.search_sticker(query), "search_sticker")
        if analysis.get_sticker_recommend:
            await self._execute(self.get_sticker_recommend(), "get_sticker_recommend")
        if sticker_id := analysis.send_sticker:
            await self._execute(self.processor.sticker_tools.send_sticker(sticker_id), "send_sticker")
        if nickname := analysis.calculate_luck_value:
            await self._execute(tool_manager.calculate_luck_value(nickname), "calculate_luck_value")
        if note := analysis.push_note:
            await self._execute(tool_manager.push_note(note.text, note.expire_hours, note.keywords), "push_note")
        if query := analysis.query_image:
            await self._execute(self.processor.query_image(query.image_id, query.query_prompt), "query_image")
        if timer := analysis.set_timer:
            await self._execute(self.processor.session.set_timer(timer.delay, timer.description), "set_timer")
        if image_id := analysis.save_sticker:
            await self._execute(self.processor.sticker_tools.save_sticker(image_id), "save_sticker")
        if prompt := analysis.ask_ai:
            await self._execute(self.processor.ai_agent.ask_ai(prompt), "ask_ai")
        if video := analysis.describe_bilibili_video:
            await self._execute(self._describe_bilibili_video(video), "describe_bilibili_video")
        if query := analysis.search_abbreviation:
            await self._execute(tool_manager.search_abbreviation(query), "search_abbreviation")
        if question := analysis.request_wolfram_alpha:
            await self._execute(request_wolfram_alpha(question), "request_wolfram_alpha")
        if keyword := analysis.web_search:
            await self._execute(tool_manager.web_search(keyword), "web_search")
        if url := analysis.browse_webpage:
            await self._execute(tool_manager.browse_webpage(url), "browse_webpage")
        if reaction := analysis.reaction:
            await self._execute(self.send_reaction(reaction.message_id, reaction.reaction), "reaction")