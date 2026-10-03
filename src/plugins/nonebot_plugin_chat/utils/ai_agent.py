import asyncio
import time

from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_openai import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message, get_message

from .tool_manager import ToolManager


class AskAISession:
    """ask_ai 工具的异步执行后端。

    ask_ai 不做任何等待：每次调用都立即把研究任务丢到后台执行并返回一条受理提示，
    任务结束后再通过事件（trigger_mode="all"）把结果汇报给会话。
    """

    def __init__(self, user_id: str, tool_manager: ToolManager) -> None:
        self.user_id = user_id
        self.tool_manager = tool_manager
        self.functions = []
        # 正在执行的查询 -> 后台任务，同一个 query 复用同一个任务，避免模型重复调用时重复消耗
        self.tasks: dict[str, asyncio.Task] = {}

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

        if (running := self.tasks.get(query)) is not None and not running.done():
            logger.info(f"Ask AI 已存在相同的查询，复用正在执行的任务 (query={query!r})")
            return await self.tool_manager.text("ask_ai.accepted")

        task = asyncio.create_task(self.run_query(query))
        self.tasks[query] = task
        # 只在这个 query 仍登记着自己时移除，避免误删之后新登记的同名任务
        task.add_done_callback(lambda finished: self._discard(query, finished))
        logger.info(f"Ask AI 已将查询转入后台执行 (query={query!r})")
        return await self.tool_manager.text("ask_ai.accepted")

    def _discard(self, query: str, finished: asyncio.Task) -> None:
        if self.tasks.get(query) is finished:
            del self.tasks[query]

    async def run_query(self, query: str) -> None:
        """后台执行查询，并把结果或失败信息作为事件汇报给会话"""
        start_time = time.monotonic()
        try:
            result = await self.fetch_answer(query)
        except asyncio.CancelledError:
            logger.info(f"Ask AI 后台任务被取消 (query={query!r})")
            raise
        except Exception as e:
            logger.exception(f"Ask AI 后台任务执行失败 (query={query!r})")
            prompt_key, prompt_args = "ask_ai.failed_prompt", (query, e)
        else:
            logger.info(f"Ask AI 后台任务已完成 (query={query!r}, 耗时 {time.monotonic() - start_time:.0f} 秒)")
            prompt_key, prompt_args = "ask_ai.result_prompt", (query, result)

        await self.report_result(prompt_key, prompt_args)

    async def report_result(self, prompt_key: str, prompt_args: tuple) -> None:
        """通过触发类型为 all 的事件向会话汇报后台任务的结果"""
        processor = self.tool_manager.processor
        if processor is None:
            logger.error("Ask AI 无法汇报结果：processor 未设置。")
            return
        try:
            prompt = await self.tool_manager.text(prompt_key, *prompt_args)
        except Exception:
            logger.exception("Ask AI 结果文案渲染失败，改用原始数据汇报。")
            prompt = f"[事件] ask_ai 请求「{prompt_args[0]}」的处理结果：{prompt_args[-1]}"

        try:
            await processor.session.add_event(prompt, trigger_mode="all")
        except Exception:
            # 入队失败时结果会永久丢失，退而直接补发一条消息，至少让用户拿到结果
            logger.exception("Ask AI 事件入队失败，尝试直接发送结果。")
            try:
                session = processor.session
                await UniMessage(prompt).send(target=session.target, bot=session.bot)
            except Exception:
                logger.exception("Ask AI 直接发送结果也失败，结果已丢失。")
