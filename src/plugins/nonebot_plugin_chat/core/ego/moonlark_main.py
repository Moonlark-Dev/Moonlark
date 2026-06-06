"""Moonlark 意识主模块

严格按照 MoonlarkEgo0528.txt 设计文档实现。
不兼容旧代码，全部重构。
"""

import asyncio
from datetime import date, datetime
from typing import Any, Literal, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter
from nonebot_plugin_openai.utils.chat import MessageFetcher, fetch_json, fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...lang import lang
from ...models import (
    ActionDecisionResponse,
    DiaryEntry,
    DiaryProcessResponse,
    MainSessionActionHistory,
    PrivateChatSession,
)
from ...utils.instant_mem import get_instant_memories
from ...utils.prompt import get_prompt_text
from ...utils.status_manager import get_status_manager
from ..session import groups
from .action_advisor import ActionAdvisor
from .blog_writer import BlogWriter

from nonebot_plugin_openai.types import Message as OpenAIChatMessage
from openai.types.chat import ChatCompletionMessage
from .proactive_chat_ctrl import ProactiveChatController
from .self_action_ctrl import SelfActionController
from .sleep_controller import SleepController


class ActionDecider:

    MAX_TOOL_RETRY: int = 2  # 文本回退最大重试次数

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self.lang = moonlark_main.lang_str
        self.lock = asyncio.Lock()
        self.loop_task: Optional[asyncio.Task] = None
        self.fetcher: Optional[MessageFetcher] = None

    async def setup(self) -> None:
        self.fetcher = await self.create_fetcher()

    async def create_fetcher(self) -> MessageFetcher:
        messages = [
            generate_message(
                await lang.text(
                    "moonlark_main.prompt",
                    self.moonlark_main.lang_str,
                    await get_prompt_text("identity"),
                    await self.moonlark_main.get_friends(),
                ),
                "system",
            ),
            await self.generate_message(
                ("online\n\n" "## 今日已进行的动作\n" f"{await self.moonlark_main._get_today_actions_text()}")
            ),
        ]
        fetcher = await MessageFetcher.create(
            messages,
            identify="ActionDecider",
            functions=[
                AsyncFunction(
                    func=self.moonlark_main.sleep_controller.sleep,
                    description=await lang.text("moonlark_main.tools.sleep.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.self_action.start_action,
                    description=await lang.text("moonlark_main.tools.start_action.description", self.lang),
                    parameters={
                        "activity": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.start_action.activity", self.lang),
                            required=True,
                        ),
                    },
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.start_new_blog,
                    description=await lang.text("moonlark_main.tools.start_new_blog.description", self.lang),
                    parameters={
                        "topic": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.start_new_blog.topic", self.lang),
                            required=True,
                        ),
                        "prompt": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.start_new_blog.prompt", self.lang),
                            required=True,
                        ),
                    },
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.blog_publish_draft,
                    description=await lang.text("moonlark_main.tools.blog_publish_draft.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.blog_drop_draft,
                    description=await lang.text("moonlark_main.tools.blog_drop_draft.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.get_blog_state,
                    description=await lang.text("moonlark_main.tools.get_blog_state.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.proactive_chat.send_private_message,
                    description=await lang.text("moonlark_main.tools.send_private_message.description", self.lang),
                    parameters={
                        "target": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.send_private_message.target", self.lang),
                            required=True,
                        ),
                        "content_hint": FunctionParameter(
                            type="string",
                            description=await lang.text(
                                "moonlark_main.tools.send_private_message.content_hint", self.lang
                            ),
                            required=True,
                        ),
                        "wait_for": FunctionParameter(
                            type="integer",
                            description=await lang.text("moonlark_main.tools.send_private_message.wait_for", self.lang),
                            required=False,
                        ),
                    },
                ),
            ],
            pre_function_call=self.pre_function_call,
            post_function_call=self._post_function_call,
            on_tool_round_complete=self._on_tool_round,
            reasoning_effort="medium",
            tool_choice="required",
        )
        return fetcher

    async def _on_tool_round(self) -> None:
        """工具调用完成但模型未输出文本时的回调。

        当 request() 不 yield（content 为空）时，loop() 拿不到控制权，
        此回调在 insert_message_queue flush 之前执行，确保 timer 消息能注入上下文。
        """
        logger.info("[ActionDecider] 工具调用完成（无文本输出），等待 60 秒后注入 timer")
        await asyncio.sleep(60)
        await self.on_event("timer")

    async def loop(self) -> None:
        if self.lock.locked():
            return
        async with self.lock:
            try:
                if self.fetcher is None:
                    self.fetcher = await self.create_fetcher()
                async for message in self.fetcher.fetch_message_stream():
                    # 检查 sleep 工具是否已被触发（工具调用过程中设置 sleep_mode=True）
                    if self.moonlark_main.state.get("sleep_mode", False):
                        logger.info("[ActionDecider] 已进入睡眠模式，停止决策循环")
                        break

                    # 参考 MessageQueue._fetch_reply() 的检测方式：
                    # 检查 fetcher 底层 session 中最后一条消息是否有 tool_calls
                    last_msg = self.fetcher.session.messages[-1] if self.fetcher.session.messages else None
                    has_tool_calls = isinstance(last_msg, ChatCompletionMessage) and last_msg.tool_calls is not None

                    if not has_tool_calls:
                        logger.warning(f"[ActionDecider] 模型未调用工具，输出文本: {message[:200]}")
                        self.fetcher.session.insert_message(
                            generate_message(
                                "你的回复必须调用一个工具来执行决策，不能直接输出文本。请立即调用工具。",
                                "user",
                            )
                        )
                        continue

                    # 工具调用结果由 post_function_call 记录
                    logger.info(f"[ActionDecider] {message}")
                    # 记录模型本次输出的文本
                    if message:
                        await self._record_diary_entry("[思考] " + message)
                    await asyncio.sleep(60)
                    await self.on_event("timer")
            except asyncio.CancelledError:
                logger.info("[ActionDecider] 决策循环被取消")
            except Exception as e:
                logger.exception(e)

    async def _post_function_call(self, result: str) -> str:
        """工具调用完成后记录返回结果到日记"""
        content = str(result)
        if len(content) > 500:
            try:
                content = await fetch_message(
                    [
                        generate_message(
                            "请用 1-2 句话总结以下工具调用结果，保留关键信息，不要添加额外解释。",
                            "system",
                        ),
                        generate_message(content, "user",
                        ),
                    ],
                    identify="ActionDecider - SummarizeToolResult",
                    reasoning_effort="low",
                )
                if not content:
                    content = str(result)[:500] + "..."
            except Exception as e:
                logger.warning(f"[Diary] 总结工具结果失败，回退截断: {e}")
                content = str(result)[:500] + "..."
        await self._record_diary_entry("[动作结果] " + content)
        return result

    async def _record_diary_entry(self, text: str) -> None:
        """记录一条文本到日记条目表"""
        try:
            async with get_session() as session:
                session.add(DiaryEntry(content=text))
                await session.commit()
            logger.debug(f"[Diary] Recorded: {text[:60]}...")
        except Exception as e:
            logger.warning(f"[Diary] Failed to record: {e}")

    async def pre_function_call(
        self, call_id: str, name: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        self.moonlark_main._update_decision_history(f"{name}({params})")
        # 记录工具调用到日记
        args_str = str(params)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        await self._record_diary_entry(f"[动作] {name}({args_str})")
        return call_id, name, params

    async def generate_message(self, reason) -> OpenAIChatMessage:
        notes_text = await self.moonlark_main.get_relevant_notes()
        instant_mem = await self.moonlark_main.summary_instant_memory()
        # 记录群聊事件总结到日记
        if instant_mem and instant_mem not in ("暂无群聊记忆。", "记忆汇总失败。"):
            await self._record_diary_entry("[群聊事件] " + instant_mem)
        return generate_message(
            await lang.text(
                "moonlark_main.user",
                self.lang,
                reason,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                instant_mem,
                notes_text,
            ),
            "user",
        )

    async def on_event(self, reason: str) -> None:
        if self.fetcher:
            self.fetcher.session.insert_message(
                await self.generate_message(reason),
            )
            return
        logger.warning(f"Fetcher 未初始化，已忽略事件: {reason}")

    def reset(self) -> None:
        """重置 ActionDecider 状态。

        取消正在运行的循环任务，并清理 fetcher 以便下次重新 setup。
        """
        if self.loop_task is not None:
            self.loop_task.cancel()
            self.loop_task = None
        # 清除 fetcher，使下次 loop() 调用时通过 getattr 检测重新 setup
        self.fetcher = None


class MoonlarkMain:
    """Moonlark 意识主模块"""

    def __init__(self, lang_str: str = "zh_hans") -> None:
        self.lang_str = lang_str

        # 子控制器
        self.sleep_controller = SleepController(self)
        self.blog_writer = BlogWriter(self)
        self.proactive_chat = ProactiveChatController(self)
        self.self_action = SelfActionController(self)
        self.action_advisor = ActionAdvisor(self)
        self.action_decider = ActionDecider(self)

        # 心情：直接用外部 StatusManager
        self.status_manager = get_status_manager()

        # 内部状态
        self.state: dict = {
            "sleep_mode": False,
            "last_decision_time": None,
            "decision_history": [],
            "instant_memory_summary": "",
            "last_summary_time": None,
            "injected_note_ids": [],
        }

        # MoonlarkMain 定时器（每5分钟，清醒时触发 action_decider.loop）
        scheduler.scheduled_job("interval", minutes=5, id="moonlark_main_timer")(self._on_timer)

        # 日记定时器（每天凌晨 2 点）
        scheduler.scheduled_job("cron", hour=2, id="moonlark_diary")(self.generate_diary)

    async def summary_instant_memory(self) -> str:
        tasks = [
            session.instant_memory_manager.generate()
            for session in groups.values()
            if session.instant_memory_manager.message_cache
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        last_summary_time = self.state.get("last_summary_time")
        memories = get_instant_memories()
        if last_summary_time:
            memories = [m for m in memories if m["create_time"] > last_summary_time]
        self.state["last_summary_time"] = datetime.now()
        if not memories:
            self.state["instant_memory_summary"] = "暂无群聊记忆。"
            return self.state["instant_memory_summary"]

        memory_lines = []
        for mem in memories:
            time_str = mem["create_time"].strftime("%H:%M")
            ctx = mem.get("name", mem.get("ctx_id", ""))
            memory_lines.append(f"[{time_str}][{ctx}] {mem['content']}")

        try:
            summary = await fetch_message(
                [
                    generate_message(
                        await lang.text("moonlark_main.summarize.system", self.lang_str),
                        "system",
                    ),
                    generate_message(
                        await lang.text("moonlark_main.summarize.user", self.lang_str, "\n".join(memory_lines)),
                        "user",
                    ),
                ],
                identify="MoonlarkMain - Summary Instant Memory",
                reasoning_effort="low",
            )
            self.state["instant_memory_summary"] = summary
        except Exception as e:
            logger.exception(f"[MoonlarkMain] 汇总即时记忆失败: {e}")
            self.state["instant_memory_summary"] = "记忆汇总失败。"

        return self.state["instant_memory_summary"]

    async def get_relevant_notes(self) -> str:
        """获取相关的备忘录，使用 ActionDecider 的全部上下文进行筛选"""
        from ...utils.note_manager import NoteManager

        try:
            # 获取 ActionDecider 的全部上下文文本
            context_text = ""
            if hasattr(self.action_decider, "fetcher") and self.action_decider.fetcher:
                for msg in self.action_decider.fetcher.session.messages:
                    content = None
                    if isinstance(msg, dict):
                        content = msg.get("content")
                    elif hasattr(msg, "content"):
                        content = msg.content
                    if content:
                        context_text += str(content) + "\n"

            if not context_text:
                return "暂无备忘录。"

            # 使用固定的 context_id，获取所有其他上下文的 Note
            note_manager = NoteManager("moonlark_main")
            _, notes_from_other = await note_manager.filter_note(context_text)
            all_notes = await note_manager.get_notes(except_current_context=True)

            # 合并：无关键词的无条件加入 + filter_note 匹配到的
            matched_ids = {n.id for n in notes_from_other}
            final_notes = []
            for note in all_notes:
                if note.id in self.state["injected_note_ids"]:
                    continue  # 跳过已注入的
                if not note.keywords or note.id in matched_ids:
                    final_notes.append(note)

            if not final_notes:
                return "暂无新的备忘录。"

            # 记录已注入的 ID
            self.state["injected_note_ids"].extend([n.id for n in final_notes])

            # 格式化
            lines = []
            for note in final_notes:
                created_time = datetime.fromtimestamp(note.created_time).strftime("%m-%d %H:%M")
                expire_info = ""
                if note.expire_time:
                    expire_info = f" (过期: {note.expire_time.strftime('%m-%d %H:%M')})"
                lines.append(f"[{created_time}]{expire_info} {note.content}")
                if note.keywords:
                    lines.append(f"  关键词: {note.keywords}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 获取备忘录失败: {e}")
            return "获取备忘录失败。"

    async def handle_mention(self, chat_context: list) -> bool:
        """当被 @ 或提及时调用。

        若不在睡眠状态，返回 False（正常回复）。
        若在睡眠状态，交给 SleepController 判断是否唤醒（内部处理 wake_up）。
        """
        if not self.state["sleep_mode"]:
            return False
        return await self.sleep_controller.handle_mention(chat_context)

    # ========================================================================
    # 状态收集
    # ========================================================================

    def _collect_state(self) -> dict:
        mood, mood_reason = self.status_manager.get_status()
        blog_status = self.blog_writer.get_status()
        proactive_info = self.proactive_chat.get_cooldown_info()
        self_action_status = self.self_action.get_status()

        return {
            "sleep_mode": self.state["sleep_mode"],
            "blog_status": blog_status["status"],
            "draft": blog_status["draft"],
            "cooldown_remaining": blog_status["cooldown_remaining"],
            "last_blog_time": blog_status["last_blog_time"],
            "proactive_info": proactive_info,
            "self_action": self_action_status,
            "mood": {
                "emotion": mood.value,
                "intensity": self.status_manager.get_mood_retention(),
                "reason": mood_reason or "",
            },
        }

    def _update_decision_history(self, action_desc: str) -> None:
        self.state["decision_history"].append(
            {
                "time": datetime.now().isoformat(),
                "action": action_desc,
            }
        )
        self.state["decision_history"] = self.state["decision_history"][-5:]

        # 持久化到数据库
        asyncio.create_task(self._persist_action(action_desc))

    async def _persist_action(self, action_desc: str) -> None:
        """将动作记录持久化到数据库"""
        try:
            async with get_session() as session:
                record = MainSessionActionHistory(
                    start_time=datetime.now(),
                    action={"action": action_desc},
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 持久化动作记录失败: {e}")

    async def _get_today_actions_text(self) -> str:
        """获取今天已进行过的动作列表，供 ActionDecider 首条消息使用"""
        try:
            today_start = datetime.combine(date.today(), datetime.min.time())
            async with get_session() as session:
                result = await session.execute(
                    select(MainSessionActionHistory)
                    .where(MainSessionActionHistory.start_time >= today_start)
                    .order_by(MainSessionActionHistory.start_time)
                )
                records = result.scalars().all()

            if not records:
                return ""

            lines = []
            for r in records:
                time_str = r.start_time.strftime("%H:%M")
                action_name = r.action.get("action", str(r.action))
                lines.append(f"[{time_str}] {action_name}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 获取今日动作历史失败: {e}")
            return ""

    # ========================================================================
    # 日记
    # ========================================================================

    async def generate_diary(self) -> None:
        """每日凌晨 2 点生成日记并写入笔记"""
        try:
            # 1. 读取近 24h 的日记条目
            entries = await self._fetch_diary_entries(hours=24)
            if not entries:
                logger.info("[Diary] 近 24h 无日记条目，跳过")
                return

            # 2. 格式化为可读文本
            context = self._format_diary_context(entries)

            # 3. 生成身份信息
            identity_prompt = await get_prompt_text("identity")

            # 4. 第一次调用：生成日记正文
            diary_text = await fetch_message(
                [
                    generate_message(
                        await lang.text(
                            "diary.system",
                            self.lang_str,
                            identity_prompt,
                        ),
                        "system",
                    ),
                    generate_message(
                        await lang.text(
                            "diary.user",
                            self.lang_str,
                            context,
                        ),
                        "user",
                    ),
                ],
                identify="MoonlarkMain - Generate Diary",
                reasoning_effort="low",
            )

            if not diary_text or not diary_text.strip():
                logger.warning("[Diary] LLM 生成的日记为空")
                return

            # 5. 第二次调用：生成关键词 + 过期时间
            processed = await fetch_json(
                [
                    generate_message(
                        await lang.text(
                            "diary_process.system",
                            self.lang_str,
                        ),
                        "system",
                    ),
                    generate_message(
                        await lang.text(
                            "diary_process.user",
                            self.lang_str,
                            diary_text,
                        ),
                        "user",
                    ),
                ],
                DiaryProcessResponse,
                identify="MoonlarkMain - Diary Process",
                reasoning_effort="low",
            )

            # 6. 写入笔记
            from ...utils.note_manager import NoteManager

            note_manager = NoteManager("moonlark_diary")
            await note_manager.create_note(
                content=diary_text,
                keywords=processed.keywords,
                expire_hours=processed.expire_hours,
            )
            logger.info(f"[Diary] 日记已生成并存入笔记: {processed.keywords}")

            # 7. 清理已使用的日记条目
            await self._cleanup_diary_entries(before=entries[-1].created_at)

        except Exception as e:
            logger.exception(f"[Diary] 日记生成失败: {e}")

    async def _fetch_diary_entries(self, hours: int = 24) -> list[DiaryEntry]:
        """获取近 N 小时的日记条目"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=hours)
        async with get_session() as session:
            result = await session.execute(
                select(DiaryEntry)
                .where(DiaryEntry.created_at >= cutoff)
                .order_by(DiaryEntry.created_at)
            )
            return list(result.scalars().all())

    def _format_diary_context(self, entries: list[DiaryEntry]) -> str:
        """将日记条目格式化为可读文本"""
        lines = []
        for entry in entries:
            time_str = entry.created_at.strftime("%H:%M")
            lines.append(f"[{time_str}] {entry.content}")
        return "\n".join(lines)

    async def _cleanup_diary_entries(self, before: datetime) -> None:
        """清理指定时间之前的日记条目"""
        try:
            async with get_session() as session:
                await session.execute(
                    select(DiaryEntry).where(DiaryEntry.created_at < before)
                )
                from sqlalchemy import delete
                await session.execute(
                    delete(DiaryEntry).where(DiaryEntry.created_at < before)
                )
                await session.commit()
                logger.debug("[Diary] 已清理过期日记条目")
        except Exception as e:
            logger.warning(f"[Diary] 清理日记条目失败: {e}")

    # ========================================================================
    # 定时器
    # ========================================================================

    async def _on_timer(self) -> None:
        """定时器回调（每5分钟）。睡眠时不触发。

        确保不会重复创建多个 loop task。
        """
        if self.state["sleep_mode"]:
            return
        if self.action_decider.loop_task is not None and not self.action_decider.loop_task.done():
            logger.debug("[MoonlarkMain] ActionDecider 循环已在运行，跳过此触发")
            return
        self.action_decider.loop_task = asyncio.create_task(self.action_decider.loop())

    # ========================================================================
    # 供外部调用的接口
    # ========================================================================

    def on_message_received(self) -> None:
        self.sleep_controller.handle_message()

    def on_reply_sent(self) -> None:
        self.sleep_controller.handle_reply()

    async def on_private_message_replied(self, user_id: str) -> None:
        await self.proactive_chat.update_reply_status(user_id, replied=True)

    def get_minutes_since_last_group_message(self) -> float:
        """获取距离最近一次群内发言的分钟数"""
        from ..session import groups

        dt = datetime.now()
        last_msg_time = None
        for group in groups.values():
            if group.cached_messages:
                msg_time = group.cached_messages[-1]["send_time"]
                if last_msg_time is None or msg_time > last_msg_time:
                    last_msg_time = msg_time
        if last_msg_time is None:
            return 60.0
        return (dt - last_msg_time).total_seconds() / 60.0

    # ========================================================================
    # 子会话接口（供 session.base 调用）
    # ========================================================================

    async def submit_action_decision(
        self,
        session_id: str,
        do: str,
        duration: Optional[int] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        try:
            session_info = f"会话ID: {session_id}"
            if session_id in groups:
                session_info = await groups[session_id].get_session_name()

            cached_messages = ""
            if session_id in groups:
                cached_messages = await groups[session_id].get_cached_messages_string(
                    length=10, include_self_message=True
                )

            system_prompt = await lang.text(
                "moonlark_main.action_request.system",
                self.lang_str,
                await get_prompt_text("identity"),
                self._get_additional_prompt_text(),
                self._get_recent_actions_text(),
            )
            user_prompt = await lang.text(
                "moonlark_main.action_request.user",
                self.lang_str,
                session_info,
                do,
                str(duration) if duration else "未指定",
                cached_messages or "无消息",
            )
            result = await fetch_json(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                ActionDecisionResponse,
                identify="MoonlarkMain - Action Request Decision",
                reasoning_effort="low",
            )

            if result.approved and result.allocated_time > 0:
                await self.self_action.start_action(do)

            if future and not future.done():
                key = (
                    "moonlark_main.action_request.result_approved"
                    if result.approved
                    else "moonlark_main.action_request.result_denied"
                )
                future.set_result(await lang.text(key, self.lang_str, do, result.allocated_time))
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"决策失败: {e}")

    async def submit_sleep_request(self, session_id: str, future: Optional[asyncio.Future] = None) -> None:
        if future and not future.done():
            future.set_result("已提交睡觉申请，等待决策...")

    async def submit_sleep_decision(
        self,
        session_id: str,
        deal_type: Literal["ready", "delay"],
        delay_minutes: Optional[int] = None,
        reason: Optional[str] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        try:
            result = await self.sleep_controller.submit_sleep_decision(
                deal_type,
                delay_minutes or 5,
                reason or "",
            )
            if future and not future.done():
                future.set_result(result)
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"决策失败: {e}")

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _get_recent_actions_text(self) -> str:
        lines = [f"[{h['time']}] {h['action']}" for h in self.state["decision_history"]]
        return "\n".join(lines) if lines else ""

    def _get_additional_prompt_text(self) -> str:
        mood, mood_reason = self.status_manager.get_status()
        return f"心情：{mood.value} (强度: {self.status_manager.get_mood_retention():.2f}; 原因: {mood_reason or '无'})"

    async def get_friends(self) -> str:
        friend_list = []
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                from nonebot_plugin_larkuser.utils.user import get_user

                user = await get_user(friend_record.user_id)
                friend_list.append(
                    await lang.text(
                        "moonlark_main.friend",
                        self.lang_str,
                        user.get_nickname(),
                        user.get_display_fav(),
                        await user.get_fav_level(),
                        datetime.fromtimestamp(friend_record.last_message_time).isoformat(),
                        (
                            datetime.fromtimestamp(friend_record.last_proactive_message_time).isoformat()
                            if friend_record.last_proactive_message_time
                            else await lang.text("moonlark_main.not_chatted_private", self.lang_str)
                        ),
                    )
                )
        return await lang.text(
            "moonlark_main.friends", self.lang_str, "\n".join(friend_list), await get_prompt_text("favorability")
        )


# 全局实例
moonlark_main = MoonlarkMain()


async def init_moonlark_main() -> None:
    await moonlark_main.action_decider.setup()
    await moonlark_main._on_timer()
    logger.info("[MoonlarkMain] 初始化完成")
