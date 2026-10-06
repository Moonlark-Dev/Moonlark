import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from nonebot.log import logger
from nonebot_plugin_openai import generate_message
from nonebot_plugin_openai.types import Message as OpenAIMessage
from nonebot_plugin_openai.utils.chat import MessageFetcher

from nonebot_plugin_chat.enums import FetchStatus
from nonebot_plugin_chat.utils.role import get_role

from ..utils.image_format import image_data_url, normalize_image
from ..utils.timing_stats import timing_stats_manager
from .context import ChatContext, ContextMessage, MessageCursor, MessageCursorClosed

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.processor import MessageProcessor

# Jev 判定「需要回复但没发消息」时，最多提示模型补发的次数
MAX_REPLY_REMINDERS = 2


class MessageQueue:
    """向 LLM 发起请求的消息队列

    消息本身由 :class:`~nonebot_plugin_chat.core.context.ChatContext` 持有，
    MessageQueue 只负责：从 context 构建 LLM 消息列表、在请求期间锁定 context、
    把请求产生的消息交回 context 解析，并把 processor 推送的增量消息拉进本次请求。
    """

    def __init__(
        self,
        processor: "MessageProcessor",
    ) -> None:
        self.processor = processor
        # chat context 由 message queue 实例化，一个 message queue 对应一个 context
        self.context = ChatContext(processor.session)
        self.context.set_lock_timeout_handler(self._on_lock_timeout)
        self.fetcher: Optional[MessageFetcher] = None
        self.fetcher_lock = asyncio.Lock()
        self.continuous_response = False
        self.fetcher_task = None
        self.last_thought: Optional[str] = None
        self.last_response: Optional[Any] = None

    @property
    def messages(self) -> list[OpenAIMessage]:
        """当前上下文对应的 LLM 消息列表（只读快照）"""
        return [message.to_openai() for message in self.context.messages if message.in_llm_context]

    async def _on_lock_timeout(self) -> None:
        """chat context 锁定超时：以失败结束本轮请求"""
        logger.warning("chat context 锁定超时，取消正在进行的 LLM 请求")
        await self.stop_fetcher()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """恢复上下文（由 MessageProcessor 在启动时调用）"""
        await self.context.start()

    async def save_to_db(self) -> None:
        await self.context.save()

    async def reset_context(self) -> None:
        """重置上下文：保存现有记录后切换到新的 context_index"""
        await self.context.reset()

    async def _create_fetcher(self) -> MessageFetcher:
        messages = await self.context.build_openai_messages()
        fetcher = await MessageFetcher.create(
            messages,
            False,
            identify="Chat",
            functions=await self.processor.tool_manager.select_tools("group"),
            pre_function_call=self.processor.send_function_call_feedback,
            post_function_call=self.processor.send_function_call_result,
            reasoning_effort="medium",
        )
        fetcher.session.set_custom_trace_id(self.context.thread_id)
        return fetcher

    async def stop_fetcher(self) -> None:
        if self.fetcher_task:
            self.fetcher_task.cancel()

    async def _ensure_system_prompt(self) -> None:
        await self.context.ensure_system_prompt()

    # ------------------------------------------------------------------
    # 请求
    # ------------------------------------------------------------------

    async def fetch_reply(self) -> None:
        if self.fetcher_lock.locked():
            return

        session_id = self.processor.session.session_id
        timing_stats_manager.record_fetch_start(session_id)

        async with self.fetcher_lock:
            self.fetcher_task = asyncio.create_task(self._fetch_reply())
            try:
                status = await self.fetcher_task
            except asyncio.CancelledError:
                # chat context 锁定超时会取消 fetcher task；外层任务自身被取消时继续向上抛
                current = asyncio.current_task()
                if current is not None and current.cancelling() > 0:
                    raise
                logger.warning("LLM 请求已被取消（chat context 锁定超时）")
                status = FetchStatus.FAILED
            logger.info(f"Reply fetcher ended with status: {status.name}")

        if self.continuous_response and self.processor.session.get_session_type() == "group":
            self.continuous_response = False

        timing_stats_manager.record_fetch_end(session_id)

    async def _sync_with_context(self, cursor: MessageCursor) -> None:
        """把完整消息列表交回 chat context 解析，再拉取增量消息推给本次请求"""
        if self.fetcher is None:
            return
        await cursor.submit(self.fetcher.session.messages)
        for message in cursor.drain():
            self.fetcher.session.messages.append(message.to_openai())

    async def _fetch_reply(self) -> FetchStatus:
        from .ego.moonlark_main import moonlark_main
        from ..utils.jev_judge import apply_reply_evaluation, evaluate_reply

        moonlark_main.on_reply_sent()

        state = FetchStatus.SUCCESS

        messages = self.messages
        if not messages:
            return FetchStatus.SKIP
        if get_role(messages[-1]) == "assistant":
            return FetchStatus.SKIP

        # provider 缓存超过 10 分钟后会被清除，此时清理不再相关的历史 block
        try:
            if await self.context.run_sliding_window():
                logger.info("已执行滑动窗口清理")
        except Exception as e:
            logger.warning(f"滑动窗口清理失败: {e}")

        try:
            cursor = await self.context.acquire_cursor()
        except RuntimeError as e:
            logger.warning(f"无法锁定 chat context: {e}")
            return FetchStatus.FAILED

        round_start = datetime.now()
        outputs: list[str] = []
        reply_reminders = 0
        try:
            self.fetcher = await self._create_fetcher()
            if self.fetcher is None:
                logger.error("Failed to create fetcher: _create_fetcher() returned None")
                state = FetchStatus.FAILED
                return state

            reply_baseline = len(self.fetcher.session.messages)
            await self._sync_with_context(cursor)
            while True:
                async for message in self.fetcher.fetch_message_stream():
                    if message:
                        outputs.append(str(message))

                await self._sync_with_context(cursor)
                evaluation = await evaluate_reply(
                    self.processor,
                    list(self.fetcher.session.messages[reply_baseline:]),
                    outputs,
                    round_start,
                )
                if evaluation is None:
                    break
                if (
                    evaluation.reply_required
                    and not self._has_sent_message_since(round_start)
                    and reply_reminders < MAX_REPLY_REMINDERS
                ):
                    reply_reminders += 1
                    logger.info("Jev 判定本轮需要回复但尚未发送消息，提示模型补发 ...")
                    # 复位 stop 并插入提示，让 fetcher 再跑一轮
                    self.fetcher.session.stop = False
                    self.fetcher.session.insert_message(
                        generate_message(await self.processor.session.text("fetcher.reply_required"), "user"),
                    )
                    continue
                await apply_reply_evaluation(self.processor, evaluation)
                break
        except MessageCursorClosed:
            logger.warning("chat context 已解锁（超时或失败），本轮请求中止")
            state = FetchStatus.FAILED
        except asyncio.CancelledError:
            state = FetchStatus.FAILED
            raise
        except Exception as e:
            logger.exception(e)
            state = FetchStatus.FAILED
        finally:
            # 模型的自然语言输出即「所思所想」，供 chat-monitor 的 thought 接口读取
            if outputs:
                self.last_thought = outputs[-1]
            if self.fetcher is not None:
                last_resp = getattr(self.fetcher.session, "last_response", None)
                if last_resp is not None:
                    self.last_response = last_resp
            try:
                await cursor.report(state == FetchStatus.SUCCESS)
            except Exception as e:  # pragma: no cover - 防御性兜底
                logger.exception(f"汇报请求状态失败: {e}")

        return state

    def _has_sent_message_since(self, since: datetime) -> bool:
        """本轮回复是否已经通过 send_message 实际发出过消息"""
        return any(
            bool(msg.get("message_id")) and (msg.get("send_time") or since) >= since
            for msg in self.processor.session.cached_messages
            if msg.get("self")
        )

    # ------------------------------------------------------------------
    # 消息推送
    # ------------------------------------------------------------------

    async def append_user_message(self, message: str | list) -> None:
        """向上下文推送一条 user 消息（事件 / 提示类）"""
        await self.context.push_user_message(message, sub_type="event")

    async def append_assistant_message(
        self,
        content: str,
        *,
        data: Optional[dict] = None,
        tool_calls: Optional[list[dict]] = None,
        display_only: Optional[bool] = None,
    ) -> ContextMessage:
        """向上下文推送一条 assistant 消息

        实际发送出去的消息（带 ``data``）默认只用于展示与统计，不进入 LLM 的消息
        列表——模型自己那一轮的输出由工具调用与工具返回表示。
        """
        if display_only is None:
            display_only = data is not None
        return await self.context.push_assistant_message(
            content, data=data, tool_calls=tool_calls, display_only=display_only
        )

    async def append_user_message_with_data(
        self,
        content: Any,
        data: Optional[dict] = None,
        *,
        sub_type: str = "message",
        trigger_type: str = "none",
        timestamp: Optional[datetime] = None,
        display_only: bool = False,
    ) -> ContextMessage:
        """向上下文推送一条完整的 user 消息（带 processor 解析出来的 json）"""
        return await self.context.push_user_message(
            content,
            sub_type=sub_type,
            data=data,
            trigger_type=trigger_type,
            timestamp=timestamp,
            display_only=display_only,
        )

    async def inject_image(self, image: bytes, mime_type: str, note: str) -> None:
        """把图片立即注入当前对话，使主模型能够直接看到图片内容

        工具调用发生在一次请求内部，此时 chat context 已被锁定，走消息推送会等到
        请求结束才生效；这里直接插入正在进行的会话，消息会在本轮工具调用结束后、
        下一次请求之前送出，随后由 chat context 解析归档。

        图片在注入前会再次校验并转换为模型支持的格式，``mime_type`` 仅作为
        调用方声明的类型参考，最终以图片真实格式为准。

        Args:
            image: 图片二进制数据
            mime_type: 图片 MIME 类型，如 image/png
            note: 随图片一起发送的说明文本
        """
        if self.fetcher is None:
            self.fetcher = await self._create_fetcher()
        normalized, actual_mime_type = normalize_image(image)
        if actual_mime_type != mime_type:
            logger.debug(f"注入图片的声明类型 {mime_type} 与实际类型 {actual_mime_type} 不一致，已按实际类型发送")
        content = [
            {"type": "text", "text": note},
            {"type": "image_url", "image_url": {"url": image_data_url(normalized, actual_mime_type)}},
        ]
        self.fetcher.session.insert_message(generate_message(content, "user"))

    def is_last_message_from_user(self) -> bool:
        messages = self.messages
        if not messages:
            return False
        return get_role(messages[-1]) == "user"
