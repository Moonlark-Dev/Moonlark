"""Moonlark 意识主模块

严格按照 MoonlarkEgo0528.txt 设计文档实现。
不兼容旧代码，全部重构。
"""

import asyncio
from datetime import date, datetime
from typing import Any, Literal, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.types import Message as OpenAIChatMessage
from nonebot_plugin_openai.utils.chat import MessageFetcher, fetch_json, fetch_message
from nonebot_plugin_openai.utils.functions import create_function_list
from nonebot_plugin_openai.utils.message import generate_message, get_message, get_message_text, get_messages
from nonebot_plugin_orm import get_session
from openai.types.chat import ChatCompletionMessage
from sqlalchemy import select

from ...lang import lang
from ...models import (
    ActionDecisionResponse,
    AgentEvent,
    DiaryPost,
    DiaryProcessResponse,
    PrivateChatSession,
)
from ...utils.status_manager import get_status_manager
from ..session import groups
from .action_advisor import ActionAdvisor
from .blog_writer import BlogWriter
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
        today_actions = await self.moonlark_main._get_today_actions_text()
        prev_diary = await self.moonlark_main._get_previous_diary()
        reason = f"online\n\n## 今日已进行的动作\n{today_actions}"
        if prev_diary:
            reason += f"\n\n{prev_diary}"
        messages = [
            await get_message(
                "system",
                "moonlark_main/system.md.jinja",
                friends=await self.moonlark_main.get_friends(),
            ),
            await self.generate_message(reason),
        ]
        functions = await create_function_list(
            [
                self.moonlark_main.sleep_controller.sleep,
                self.start_self_action,  # 改名，避免与 Chat Session 的 start_action 冲突
                self.moonlark_main.blog_writer.start_new_blog,
                self.moonlark_main.blog_writer.blog_publish_draft,
                self.moonlark_main.blog_writer.blog_drop_draft,
                self.moonlark_main.blog_writer.get_blog_state,
                self.moonlark_main.proactive_chat.send_private_message,
                self.refuse_action_request,  # 新增
                self.moonlark_main.chat,
            ],
        )
        fetcher = await MessageFetcher.create(
            messages,
            identify="ActionDecider",
            functions=functions,
            pre_function_call=self.pre_function_call,
            post_function_call=self._post_function_call,
            on_tool_round_complete=self._on_tool_round,
            reasoning_effort="medium",
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
                            ),
                        )
                        continue

                    # 工具调用结果由 post_function_call 记录
                    logger.info(f"[ActionDecider] {message}")
                    # 记录模型本次输出的文本
                    if message:
                        await self._record_event("[思考] " + message)
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
                        generate_message(
                            content,
                            "user",
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
        await self._record_event("[动作结果] " + content)
        return result

    async def _record_event(self, text: str) -> None:
        """记录一条事件到智能体事件表"""
        try:
            async with get_session() as session:
                session.add(AgentEvent(content=text))
                await session.commit()
            logger.debug(f"[AgentEvent] Recorded: {text[:60]}...")
        except Exception as e:
            logger.warning(f"[AgentEvent] Failed to record: {e}")

    async def pre_function_call(
        self,
        call_id: str,
        name: str,
        params: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        self.moonlark_main._update_decision_history(f"{name}({params})")
        # 记录工具调用到日记
        args_str = str(params)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        await self._record_event(f"[动作] {name}({args_str})")

        # 检测 pending action request 的响应
        pending = self.moonlark_main._pending_action_request
        action_tools = {
            "sleep",
            "start_self_action",
            "start_new_blog",
            "blog_publish_draft",
            "blog_drop_draft",
            "send_private_message",
        }

        if pending is not None and not pending["future"].done():
            if name == "refuse_action_request":
                reason = params.get("reason", "无")
                result_text = f"动作请求已被拒绝。原因：{reason}"
                pending["future"].set_result(result_text)
                self.moonlark_main._pending_action_request = None
            elif name in action_tools:
                # 请求的动作被接受了
                result_text = f"动作请求已被接受，Moonlark 正在执行「{pending['type']}」"
                pending["future"].set_result(result_text)
                self.moonlark_main._pending_action_request = None
        return call_id, name, params

    async def generate_message(self, reason) -> OpenAIChatMessage:
        notes_text = await self.moonlark_main.get_relevant_notes()
        chat_summary = await self.moonlark_main.summary_instant_memory()
        # 记录QQ中的事件总结到日记
        if chat_summary and chat_summary not in ("暂无聊天记录。", "聊天记录汇总失败。"):
            await self._record_event("[QQ中的事件] " + chat_summary)
        return await get_message(
            "user",
            "moonlark_main/user.md.jinja",
            reason=reason,
            summary=chat_summary,
            notes=notes_text,
        )

    async def on_event(self, reason: str) -> None:
        if self.fetcher:
            self.fetcher.session.insert_message(
                await self.generate_message(reason),
            )
            return
        logger.warning(f"Fetcher 未初始化，已忽略事件: {reason}")

    async def start_self_action(self, activity: str) -> str:
        """执行自主活动（包装 SelfActionController.start_action）"""
        return await self.moonlark_main.self_action.start_action(activity)

    async def refuse_action_request(self, reason: str) -> str:
        """拒绝来自会话的动作请求"""
        return f"[拒绝] 已拒绝动作请求。原因: {reason}"

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
            "chat_summary": "",
            "last_summary_time": None,
            "injected_note_ids": [],
        }

        # pending action request（来自 Chat Session 的 start_action 请求）
        self._pending_action_request: Optional[dict] = None

        # MoonlarkMain 定时器（每5分钟，清醒时触发 action_decider.loop）
        scheduler.scheduled_job("interval", minutes=5, id="moonlark_main_timer")(self._on_timer)

        # 日记定时器（每天凌晨 2 点）
        scheduler.scheduled_job("cron", hour=2, id="moonlark_diary")(self.generate_diary)

    async def summary_instant_memory(self) -> str:
        """从所有会话的聊天记录中提取摘要（替代原来的即时记忆汇总）"""
        from ..session import groups

        # 收集所有会话的聊天记录
        all_chat_parts = []
        for session_id, session in groups.items():
            session_name = await session.get_session_name()
            recent = await session.get_cached_messages_string(length=30, include_self_message=True)
            if recent:
                all_chat_parts.append(f"会话 {session_name}:\n{recent}")

        if not all_chat_parts:
            self.state["chat_summary"] = "暂无聊天记录。"
            return self.state["chat_summary"]

        combined = "\n\n---\n\n".join(all_chat_parts)
        try:
            messages = await get_messages(
                "summarize",
                memories=combined,
            )
            summary = await fetch_message(
                messages,
                identify="MoonlarkMain - Summary Chat History",
                reasoning_effort="low",
            )
            self.state["chat_summary"] = summary
        except Exception as e:
            logger.exception(f"[MoonlarkMain] 汇总聊天记录失败: {e}")
            self.state["chat_summary"] = "聊天记录汇总失败。"

        return self.state["chat_summary"]

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

    async def handle_mention(self, chat_context: list, session_name: str = "", nickname: str = "") -> bool:
        """当被 @ 或提及时调用。

        若不在睡眠状态，返回 False（正常回复）。
        若在睡眠状态，交给 SleepController 判断是否唤醒（内部处理 wake_up）。
        """
        if not self.state["sleep_mode"]:
            return False
        return await self.sleep_controller.handle_mention(chat_context, session_name=session_name, nickname=nickname)

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
        # 去重：如果有相同 action 的旧条目，先移除
        self.state["decision_history"] = [h for h in self.state["decision_history"] if h["action"] != action_desc]
        self.state["decision_history"].append(
            {
                "time": datetime.now().isoformat(),
                "action": action_desc,
            },
        )
        self.state["decision_history"] = self.state["decision_history"][-5:]

    async def _get_today_actions_text(self) -> str:
        """获取今天已进行过的动作列表，供 ActionDecider 首条消息使用"""
        try:
            today_start = datetime.combine(date.today(), datetime.min.time())
            async with get_session() as session:
                result = await session.execute(
                    select(AgentEvent)
                    .where(AgentEvent.created_at >= today_start, AgentEvent.content.startswith("[动作]"))
                    .order_by(AgentEvent.created_at),
                )
                records = result.scalars().all()

            if not records:
                return ""

            lines = []
            for r in records:
                time_str = r.created_at.strftime("%H:%M")
                lines.append(f"[{time_str}] {r.content}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 获取今日动作历史失败: {e}")
            return ""

    async def _get_previous_diary(self) -> str:
        """获取前一天生成的日记内容，供 ActionDecider 首条消息使用"""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(DiaryPost).order_by(DiaryPost.created_at.desc()).limit(1),
                )
                diary = result.scalar_one_or_none()
                if diary:
                    return f"## 昨日日记\n{diary.content}"
                return ""
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 获取前日日记失败: {e}")
            return ""

    # ========================================================================
    # 日记
    # ========================================================================

    async def generate_diary(self) -> None:
        """每日凌晨 2 点生成日记并写入 DiaryPost 表"""
        try:
            # 1. 读取近 24h 的日记条目
            entries = await self._fetch_diary_entries(hours=24)
            if not entries:
                logger.info("[Diary] 近 24h 无日记条目，跳过")
                return

            # 2. 格式化为可读文本
            context = self._format_diary_context(entries)

            # 3. 第一次调用：生成日记正文
            # 使用最后一次睡眠时间作为日记时间
            diary_time = self.sleep_controller.sleep_begin_time
            if diary_time:
                diary_time_str = diary_time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                diary_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            diary_messages = await get_messages("diary", context=context, current_time=diary_time_str)
            diary_text = await fetch_message(
                diary_messages,
                identify="MoonlarkMain - Generate Diary",
                reasoning_effort="low",
            )

            if not diary_text or not diary_text.strip():
                logger.warning("[Diary] LLM 生成的日记为空")
                return

            # 4. 第二次调用：生成关键词 + 过期时间
            diary_process_messages = await get_messages("diary_process", diary_text=diary_text)
            processed = await fetch_json(
                diary_process_messages,
                DiaryProcessResponse,
                identify="MoonlarkMain - Diary Process",
                reasoning_effort="low",
            )

            # 5. 计算过期时间
            from datetime import timedelta

            expire_at = datetime.now() + timedelta(hours=processed.expire_hours)

            # 6. 写入 DiaryPost 表
            async with get_session() as session:
                diary_post = DiaryPost(
                    content=diary_text,
                    keywords=processed.keywords,
                    expire_at=expire_at,
                )
                session.add(diary_post)
                await session.commit()
            logger.info(f"[Diary] 日记已生成并存入 DiaryPost: {processed.keywords}")

            # 7. 清理已使用的日记条目
            await self._cleanup_diary_entries(before=entries[-1].created_at)

        except Exception as e:
            logger.exception(f"[Diary] 日记生成失败: {e}")

    async def _fetch_diary_entries(self, hours: int = 24) -> list[AgentEvent]:
        """获取近 N 小时的智能体事件条目"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=hours)
        async with get_session() as session:
            result = await session.execute(
                select(AgentEvent).where(AgentEvent.created_at >= cutoff).order_by(AgentEvent.created_at),
            )
            return list(result.scalars().all())

    def _format_diary_context(self, entries: list[AgentEvent]) -> str:
        """将智能体事件条目格式化为可读文本"""
        lines = []
        for entry in entries:
            time_str = entry.created_at.strftime("%H:%M")
            lines.append(f"[{time_str}] {entry.content}")
        return "\n".join(lines)

    async def _cleanup_diary_entries(self, before: datetime) -> None:
        """清理指定时间之前的智能体事件条目"""
        try:
            async with get_session() as session:
                await session.execute(select(AgentEvent).where(AgentEvent.created_at < before))
                from sqlalchemy import delete

                await session.execute(delete(AgentEvent).where(AgentEvent.created_at < before))
                await session.commit()
                logger.debug("[AgentEvent] 已清理过期条目")
        except Exception as e:
            logger.warning(f"[AgentEvent] 清理条目失败: {e}")

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

    async def submit_action_request(
        self,
        session_id: str,
        type: str,
        info: str,
        reason: str,
        future: asyncio.Future,
    ) -> None:
        """处理来自 Chat Session 的 start_action 请求"""
        try:
            # 1. 如果处于睡眠状态，唤醒
            if self.state["sleep_mode"]:
                await self.sleep_controller.wake_up(f"来自会话 {session_id} 的动作请求")
                # 重置 ActionDecider 以便重建 fetcher
                self.action_decider.reset()

            # 2. 如果 SelfActionController 正在 asyncio.sleep，取消它
            if self.self_action.cancel_action():
                # 取消后已有 CancelledError 处理，不需要额外操作
                pass

            # 3. 确保 ActionDecider 的 fetcher 可用
            if self.action_decider.fetcher is None:
                self.action_decider.fetcher = await self.action_decider.create_fetcher()

            # 4. 存储 pending request
            self._pending_action_request = {
                "future": future,
                "session_id": session_id,
                "type": type,
                "info": info,
                "reason": reason,
            }

            # 5. 获取会话名称
            if session_id in groups:
                session_name = await groups[session_id].get_session_name() or session_id
            else:
                session_name = session_id

            # 6. 推送事件到 ActionDecider
            event_text = (
                f"在{session_name}中，你想进行动作：\n"
                f"类型：{type}\n"
                f"信息：{info}\n"
                f"原因：{reason}\n"
                f"你可以调用相应工具进行执行，也可以使用 refuse_action_request 工具拒绝"
            )

            await self.action_decider.on_event(event_text)

            # 7. 确保 ActionDecider 的 loop 正在运行
            if self.action_decider.loop_task is None or self.action_decider.loop_task.done():
                self.action_decider.loop_task = asyncio.create_task(self.action_decider.loop())
        except Exception as e:
            logger.exception(f"[MoonlarkMain] submit_action_request 失败: {e}")
            if future and not future.done():
                future.set_result(f"动作请求处理失败: {e}")

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
                session_info = (await groups[session_id].get_session_name()) or session_info

            cached_messages = ""
            if session_id in groups:
                cached_messages = await groups[session_id].get_cached_messages_string(
                    length=10,
                    include_self_message=True,
                )

            action_messages = await get_messages(
                "action_request",
                additional_info=self._get_additional_prompt_text(),
                recent_actions=self._get_recent_actions_text(),
                session_info=session_info,
                do=do,
                duration=str(duration) if duration else "未指定",
                cached_messages=cached_messages or "无消息",
            )
            result = await fetch_json(
                action_messages,
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

    async def chat(self, max_wait_minutes: int = 10) -> str:
        """在QQ中聊天，等待所有已初始化的会话冷却三分钟

        Args:
            max_wait_minutes: 最大等待时间（分钟），超时后返回
        """
        if not groups:
            return "没有已初始化的会话"

        cooldown_seconds = 180
        max_wait_seconds = max_wait_minutes * 60
        elapsed_total = 0
        while elapsed_total < max_wait_seconds:
            now = datetime.now()
            all_cooled = True
            for session in groups.values():
                if not session.cached_messages:
                    continue
                elapsed = (now - session.cached_messages[-1]["send_time"]).total_seconds()
                if elapsed < cooldown_seconds:
                    all_cooled = False
                    break
            if all_cooled:
                return "所有会话已冷却三分钟，可以继续决策"
            await asyncio.sleep(30)
            elapsed_total += 30
        return "等待超时，部分会话仍未冷却"

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
                    ),
                )
        return await lang.text(
            "moonlark_main.friends",
            self.lang_str,
            "\n".join(friend_list),
            await get_message_text("favorability.md.jinja"),
        )


# 全局实例
moonlark_main = MoonlarkMain()


async def init_moonlark_main() -> None:
    await moonlark_main.action_decider.setup()
    await moonlark_main._on_timer()
    logger.info("[MoonlarkMain] 初始化完成")
