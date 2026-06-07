from nonebot_plugin_openai import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message, get_message

from .tool_manager import ToolManager


class AskAISession:

    def __init__(self, user_id: str, tool_manager: ToolManager) -> None:
        self.user_id = user_id
        self.tool_manager = tool_manager
        self.functions = []

    async def setup(self) -> None:
        self.functions = await self.tool_manager.select_tools("agent")

    async def ask_ai(self, query: str) -> str:
        if not self.functions:
            await self.setup()
        fetcher = await MessageFetcher.create(
            [
                await get_message("system", "chat_agent.md.jinja"),
                generate_message(query, "user"),
            ],
            False,
            functions=self.functions,
            identify="Ask AI",
        )
        return await fetcher.fetch_last_message()
