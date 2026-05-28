"""博客编写模块

管理 Moonlark 的博客写作流程：
- 草稿管理（创建、续写、放弃、发布）
- 状态机：IDLE → DRAFTING → FINISHED → IDLE
- 冷却机制（2小时间隔）
- query_chat_history 工具（从 session 缓存检索主题）
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from ...lang import lang

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

# 状态常量
STATUS_IDLE = "IDLE"
STATUS_DRAFTING = "DRAFTING"
STATUS_FINISHED = "FINISHED"


class BlogWriter:
    """博客编写模块"""

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self.status: str = STATUS_IDLE
        self.current_draft: Optional[dict] = None
        # {
        #     "topic": str,
        #     "content": str,
        #     "word_count": int,
        #     "last_updated": datetime,
        #     "continue_count": int
        # }
        self.published_blogs: list[dict] = []
        self.last_blog_time: Optional[datetime] = None
        self.cooldown_seconds: int = 7200  # 2 小时

    def get_status(self) -> dict:
        """获取当前博客状态，供 MoonlarkMain 使用"""
        return {
            "status": self.status,
            "draft": self.current_draft,
            "last_blog_time": self.last_blog_time,
            "cooldown_remaining": self._get_cooldown_remaining(),
        }

    def _get_cooldown_remaining(self) -> int:
        """获取冷却剩余秒数"""
        if not self.last_blog_time:
            return 0
        elapsed = (datetime.now() - self.last_blog_time).total_seconds()
        return max(0, int(self.cooldown_seconds - elapsed))

    def _in_cooldown(self) -> bool:
        """是否在冷却期"""
        return self._get_cooldown_remaining() > 0

    async def handle_action(self, action_str: str) -> None:
        """处理来自 MoonlarkMain 的 blog_action 指令

        Args:
            action_str: "skip" | "start_new_topic: <主题>" | "continue_draft" | "abort_draft"
        """
        if action_str == "skip":
            return
        elif action_str.startswith("start_new_topic:"):
            topic = action_str.split(":", 1)[1].strip()
            await self._start_new_blog(topic)
        elif action_str == "continue_draft":
            await self._continue_draft()
        elif action_str == "abort_draft":
            await self._abort_draft()
        else:
            logger.warning(f"[BlogWriter] 未知的 blog_action: {action_str}")

    async def _start_new_blog(self, topic: str) -> None:
        """开始撰写新博客"""
        # 检查状态
        if self.status != STATUS_IDLE:
            logger.info(f"[BlogWriter] 当前状态为 {self.status}，无法开始新博客")
            return

        # 检查冷却
        if self._in_cooldown():
            logger.info(f"[BlogWriter] 冷却中，剩余 {self._get_cooldown_remaining()} 秒")
            return

        # 调用 LLM 生成初稿（300-500字，猫娘风格）
        try:
            system_prompt = await lang.text(
                "blog.writer.system", self.moonlark_main.lang_str
            )
            user_prompt = await lang.text(
                "blog.writer.start", self.moonlark_main.lang_str, topic
            )

            content = await fetch_message(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                identify="Blog Writer - Start",
                reasoning_effort="medium",
            )

            # 保存草稿
            self.current_draft = {
                "topic": topic,
                "content": content,
                "word_count": len(content),
                "last_updated": datetime.now(),
                "continue_count": 0,
            }
            self.status = STATUS_DRAFTING
            logger.info(f"[BlogWriter] 开始新博客: {topic}，字数: {len(content)}")

        except Exception as e:
            logger.exception(f"[BlogWriter] 生成初稿失败: {e}")

    async def _continue_draft(self) -> None:
        """续写当前草稿"""
        if self.status != STATUS_DRAFTING or not self.current_draft:
            logger.info("[BlogWriter] 当前无草稿可续写")
            return

        try:
            system_prompt = await lang.text(
                "blog.writer.system", self.moonlark_main.lang_str
            )
            user_prompt = await lang.text(
                "blog.writer.continue",
                self.moonlark_main.lang_str,
                self.current_draft["topic"],
                self.current_draft["content"],
            )

            content = await fetch_message(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                identify="Blog Writer - Continue",
                reasoning_effort="medium",
            )

            # 检查是否包含 [FINISH] 标记
            if "[FINISH]" in content:
                content = content.replace("[FINISH]", "").strip()
                self.current_draft["content"] += "\n\n" + content
                self.current_draft["word_count"] = len(self.current_draft["content"])
                self.current_draft["continue_count"] += 1
                logger.info("[BlogWriter] 检测到 [FINISH] 标记，自动发布")
                await self._publish_blog()
                return

            # 更新草稿
            self.current_draft["content"] += "\n\n" + content
            self.current_draft["word_count"] = len(self.current_draft["content"])
            self.current_draft["continue_count"] += 1
            self.current_draft["last_updated"] = datetime.now()

            logger.info(
                f"[BlogWriter] 续写完成，当前字数: {self.current_draft['word_count']}，"
                f"续写次数: {self.current_draft['continue_count']}"
            )

            # 检查是否达到发布条件
            if self.current_draft["word_count"] >= 500 or self.current_draft["continue_count"] >= 5:
                logger.info("[BlogWriter] 达到发布条件，自动发布")
                await self._publish_blog()

        except Exception as e:
            logger.exception(f"[BlogWriter] 续写失败: {e}")

    async def _abort_draft(self) -> None:
        """放弃当前草稿"""
        if self.current_draft:
            logger.info(f"[BlogWriter] 放弃草稿: {self.current_draft['topic']}")
        self.current_draft = None
        self.status = STATUS_IDLE

    async def _publish_blog(self) -> None:
        """发布博客"""
        if not self.current_draft:
            return

        try:
            from ...utils.blog import create_blog_post

            # 保存到数据库
            await create_blog_post(self.current_draft["topic"], self.current_draft["content"])

            # 记录发布信息
            self.published_blogs.append({
                "title": self.current_draft["topic"],
                "timestamp": datetime.now(),
            })
            self.last_blog_time = datetime.now()

            # 清空草稿
            self.current_draft = None
            self.status = STATUS_IDLE

            logger.info(f"[BlogWriter] 博客发布成功")

        except Exception as e:
            logger.exception(f"[BlogWriter] 发布失败: {e}")

    async def query_chat_history(self, query: str) -> str:
        """工具方法：从 session 缓存检索特定主题信息

        Args:
            query: 查询字符串（如"群聊里最近讨论过哪些前端技术？"）

        Returns:
            相关段落摘要
        """
        from ..session import groups

        # 收集所有活跃会话的最近消息
        all_sessions_info = []
        for session_id, session in groups.items():
            cached = await session.get_cached_messages_string(length=50)
            if cached:
                session_name = await session.get_session_name()
                all_sessions_info.append(f"## {session_name}\n{cached}")

        if not all_sessions_info:
            return "未找到活跃的聊天会话"

        combined = "\n\n".join(all_sessions_info)

        # 调用 LLM 检索
        try:
            system_prompt = await lang.text(
                "blog.query_chat.system", self.moonlark_main.lang_str, combined
            )
            response = await fetch_message(
                [generate_message(system_prompt, "system"), generate_message(query, "user")],
                identify="Blog Writer - Query History",
                reasoning_effort="low",
            )
            return response
        except Exception as e:
            logger.exception(f"[BlogWriter] 查询聊天记录失败: {e}")
            return "查询失败"
