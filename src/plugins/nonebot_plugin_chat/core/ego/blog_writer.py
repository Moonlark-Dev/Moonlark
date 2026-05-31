"""博客编写模块

管理 Moonlark 的博客写作流程：
- 草稿管理（创建、确认发布、取消）
- 状态机：IDLE → FINISHED → IDLE
- 冷却机制（2小时间隔）
- query_chat_history 工具（从 session 缓存检索主题）
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ...lang import lang
from ...models import BlogPost
from ...utils.prompt import get_prompt_text

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

# 状态常量
STATUS_IDLE = "IDLE"
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
            action_str: "skip" | "start_new_topic: <主题>" | "publish" | "abort"
        """
        if action_str == "skip":
            return
        elif action_str.startswith("start_new_topic:"):
            topic = action_str.split(":", 1)[1].strip()
            await self._start_new_blog(topic, "")
        elif action_str == "publish":
            await self._publish_blog()
        elif action_str == "abort":
            await self._abort_draft()
        else:
            logger.warning(f"[BlogWriter] 未知的 blog_action: {action_str}")

    async def start_new_blog(self, topic: str, prompt: str) -> str:
        if self.status != STATUS_IDLE:
            return f"当前状态为 {self.status}，无法开始新博客"

        # 检查冷却
        if self._in_cooldown():
            return f"冷却中，剩余 {self._get_cooldown_remaining()} 秒"
        
        return await self._start_new_blog(topic, prompt)
    
    async def get_blog_state(self) -> str:
        today_posts = await self._get_today_posts()
        if today_posts:
            today_text = "\n".join(f"- [{p['time']}] {p['title']}" for p in today_posts)
        else:
            today_text = "今日尚未发布博客"
        return await lang.text("moonlark_main.blog_state", self.moonlark_main.lang_str, self.status, self.current_draft, today_text)

    async def _get_today_posts(self) -> list[dict]:
        """查询今天已发布的博客"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            async with get_session() as session:
                posts = (await session.scalars(
                    select(BlogPost).where(BlogPost.create_at >= today_start)
                )).all()
                return [{"title": p.title, "time": p.create_at.strftime("%H:%M")} for p in posts]
        except Exception as e:
            logger.debug(f"[BlogWriter] 查询今日博客失败: {e}")
            return []
    
    async def blog_drop_draft(self) -> None:
        await self._abort_draft()

    async def blog_publish_draft(self) -> None:
        await self._publish_blog()

    async def _start_new_blog(self, topic: str, prompt: str) -> str:
        """撰写新博客（一次性完成，写完后等 MoonlarkMain 确认发布）"""
        # 检查状态
        
        identity_prompt = await get_prompt_text("identity")
        recent_actions = self.moonlark_main._get_recent_actions_text()
        extra_context = await self._gather_context(topic)

        system_prompt = await lang.text(
            "blog.writer.system", self.moonlark_main.lang_str, identity_prompt
        )
        user_prompt = await lang.text(
            "blog.writer.start", self.moonlark_main.lang_str, topic, prompt, recent_actions, extra_context
        )

        content = await fetch_message(
            [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
            identify="Blog Writer",
            reasoning_effort="medium",
        )

        # 保存草稿，状态设为 FINISHED（等 MoonlarkMain 确认发布）
        self.current_draft = {
            "topic": topic,
            "content": content,
            "word_count": len(content),
            "last_updated": datetime.now(),
        }
        self.status = STATUS_FINISHED
        return content

    async def _abort_draft(self) -> None:
        """取消当前草稿"""
        if self.current_draft:
            logger.info(f"[BlogWriter] 取消草稿: {self.current_draft['topic']}")
        self.current_draft = None
        self.status = STATUS_IDLE

    async def _publish_blog(self) -> None:
        """发布博客"""
        if not self.current_draft:
            logger.info("[BlogWriter] 无草稿可发布")
            return

        try:
            from ...utils.blog import create_blog_post

            await create_blog_post(self.current_draft["topic"], self.current_draft["content"])

            self.published_blogs.append({
                "title": self.current_draft["topic"],
                "timestamp": datetime.now(),
            })
            self.last_blog_time = datetime.now()

            logger.info(f"[BlogWriter] 博客发布成功: {self.current_draft['topic']}")

            self.current_draft = None
            self.status = STATUS_IDLE

        except Exception as e:
            logger.exception(f"[BlogWriter] 发布失败: {e}")

    async def _gather_context(self, topic: str) -> str:
        """收集博客写作的额外上下文：聊天记录"""
        parts = []

        # 从聊天记录中检索与主题相关的内容
        try:
            chat_result = await self.query_chat_history(topic)
            if chat_result and chat_result != "未找到活跃的聊天会话":
                parts.append("## 相关聊天记录\n\n" + chat_result)
        except Exception as e:
            logger.debug(f"[BlogWriter] 查询聊天记录失败: {e}")

        return "\n\n".join(parts) if parts else ""

    async def query_chat_history(self, query: str) -> str:
        """工具方法：从 session 缓存检索特定主题信息

        Args:
            query: 查询字符串（如"群聊里最近讨论过哪些前端技术？"）

        Returns:
            相关段落摘要
        """
        from ..session import groups

        all_sessions_info = []
        for session_id, session in groups.items():
            cached = await session.get_cached_messages_string(length=50)
            if cached:
                session_name = await session.get_session_name()
                all_sessions_info.append(f"## {session_name}\n{cached}")

        if not all_sessions_info:
            return "未找到活跃的聊天会话"

        combined = "\n\n".join(all_sessions_info)

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
