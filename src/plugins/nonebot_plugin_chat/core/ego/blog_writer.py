"""博客编写模块

- Decider：睡前运行，从当天话题中筛选一个主题（可跳过）
- Writter：根据 Decider 的结果撰写博客
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json, fetch_message
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from sqlalchemy import select

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

from ...models import BlogPost


class BlogDecision(BaseModel):
    skip: bool = False
    topic: str = ""
    outline: str = ""


class BlogTitle(BaseModel):
    title: str


class BlogWriter:
    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self.last_blog_time: Optional[datetime] = None
        self.cooldown_seconds: int = 7200

    def get_status(self) -> dict:
        return {
            "last_blog_time": self.last_blog_time,
            "cooldown_remaining": self._get_cooldown_remaining(),
        }

    def _get_cooldown_remaining(self) -> int:
        if not self.last_blog_time:
            return 0
        elapsed = (datetime.now() - self.last_blog_time).total_seconds()
        return max(0, int(self.cooldown_seconds - elapsed))

    def _in_cooldown(self) -> bool:
        return self._get_cooldown_remaining() > 0

    async def decider(self, events_text: str, plan_text: str) -> Optional[BlogDecision]:
        if self._in_cooldown():
            logger.info("[BlogWriter] 冷却中，跳过 Decider")
            return None

        messages = await get_messages("blog_decider", events=events_text, plan=plan_text)
        try:
            return await fetch_json(
                messages,
                BlogDecision,
                identify="BlogWriter - Decider",
                reasoning_effort="medium",
            )
        except Exception as e:
            logger.exception(f"[BlogWriter] Decider 失败: {e}")
            return None

    async def writter(self, decision: BlogDecision, events_text: str, plan_text: str) -> Optional[str]:
        from ...utils.weather import get_daily_weather_text, get_weekday_text

        messages = await get_messages(
            "blog_writter",
            topic=decision.topic,
            outline=decision.outline,
            events=events_text,
            plan=plan_text,
            weather=(await get_daily_weather_text()) or "",
            weekday=get_weekday_text(),
        )
        try:
            content = await fetch_message(
                messages,
                identify="BlogWriter - Writter",
                reasoning_effort="medium",
            )
            title = (
                decision.topic.strip()
                if decision.topic and decision.topic.strip()
                else await self._generate_title(content)
            )
            await self._publish(title, content)
            return content
        except Exception as e:
            logger.exception(f"[BlogWriter] Writter 失败: {e}")
            return None

    async def _generate_title(self, content: str) -> str:
        messages = await get_messages("blog_title", content=content)
        try:
            result = await fetch_json(
                messages,
                BlogTitle,
                identify="BlogWriter - Title",
                reasoning_effort="low",
            )
            title = result.title.strip()
            if title:
                return title
        except Exception as e:
            logger.exception(f"[BlogWriter] 标题生成失败: {e}")
        return "今日的博客"

    async def _publish(self, title: str, content: str) -> None:
        try:
            from ...utils.blog import create_blog_post

            await create_blog_post(title, content)
            self.last_blog_time = datetime.now()
            logger.info(f"[BlogWriter] 博客发布成功: {title}")
        except Exception as e:
            logger.exception(f"[BlogWriter] 发布失败: {e}")

    async def _get_today_posts(self) -> list[dict]:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            async with get_session() as session:
                posts = (await session.scalars(select(BlogPost).where(BlogPost.create_at >= today_start))).all()
                return [{"title": p.title, "time": p.create_at.strftime("%H:%M")} for p in posts]
        except Exception as e:
            logger.debug(f"[BlogWriter] 查询今日博客失败: {e}")
            return []
