import asyncio
import time

from nonebot.log import logger
from nonebot_plugin_openai import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message, get_message

from .tool_manager import ToolManager

# ask_ai 总运行时间上限（秒），超过后先返回“正在处理中”提示，处理完成后再通过事件汇报结果
ASK_AI_TIME_LIMIT = 180


class AskAISession:
    def __init__(self, user_id: str, tool_manager: ToolManager) -> None:
        self.user_id = user_id
        self.tool_manager = tool_manager
        self.functions = []
        self.background_tasks: set[asyncio.Task] = set()

    async def setup(self) -> None:
        self.functions = await self.tool_manager.select_tools("agent")

    async def fetch_answer(self, query: str) -> str:
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

    async def ask_ai(self, query: str) -> str:
        if not self.functions:
            await self.setup()

        # 限制总运行时间，超时后先返回提示，任务转入后台继续执行
        start_time = time.monotonic()
        fetch_task = asyncio.create_task(self.fetch_answer(query))
        timeout = max(0.0, ASK_AI_TIME_LIMIT - (time.monotonic() - start_time))
        done, _pending = await asyncio.wait({fetch_task}, timeout=timeout)
        if fetch_task in done:
            return fetch_task.result()

        logger.info(
            f"Ask AI 总运行时间已超过 {time.monotonic() - start_time:.0f} 秒，"
            "将返回处理中提示，完成后通过事件汇报结果。",
        )
        self._run_in_background(fetch_task)
        self._run_in_background(asyncio.create_task(self.report_result(query, fetch_task)))
        elapsed = int(time.monotonic() - start_time)
        return await self.tool_manager.text("ask_ai.processing", elapsed)

    def _run_in_background(self, task: asyncio.Task) -> None:
        """持有后台任务的引用直到其结束，避免任务被垃圾回收"""
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def report_result(self, query: str, fetch_task: asyncio.Task) -> None:
        """在后台任务结束后，通过触发类型为 all 的事件向会话汇报结果"""
        try:
            result = await fetch_task
        except Exception as e:
            logger.exception(f"Ask AI 后台任务执行失败 (query={query!r})")
            prompt_key, prompt_args = "ask_ai.failed_prompt", (query, e)
        else:
            prompt_key, prompt_args = "ask_ai.result_prompt", (query, result)

        processor = self.tool_manager.processor
        if processor is None:
            logger.error("Ask AI 无法汇报结果：processor 未设置。")
            return
        prompt = await self.tool_manager.text(prompt_key, *prompt_args)
        await processor.session.add_event(prompt, trigger_mode="all")
