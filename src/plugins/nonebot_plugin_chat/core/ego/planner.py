"""计划管理器

- 早上：醒来后半小时运行计划生成（最晚不超过 11:00），存储到 localstore
- 下午：13:30 运行计划修正（仅下午和晚上），更新计划文件
- 会话初始化时读取当天的计划文件注入上下文
"""

import json
import os
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

import nonebot_plugin_localstore as store
from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import get_messages
from pydantic import BaseModel

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

PLAN_DIR = store.get_data_dir("nonebot_plugin_chat")
MAX_PLAN_AGE_DAYS = 7


class PlanItem(BaseModel):
    period: str
    content: str


class PlanResponse(BaseModel):
    plan: list[PlanItem]


def _today_plan_path():
    today_str = date.today().isoformat()
    return str(PLAN_DIR / f"plan_{today_str}.json")


class Planner:
    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self._plan: Optional[list[PlanItem]] = None

    async def run_morning_plan(self) -> None:
        logger.info("[Planner] 开始生成今日计划")
        try:
            events_text = await self._gather_context()
            notes_text = await self.moonlark_main.get_relevant_notes()
            messages = await get_messages("planner_morning", events=events_text, notes=notes_text)
            result = await fetch_json(messages, PlanResponse, identify="Planner - Morning", reasoning_effort="medium")
            self._plan = result.plan
            self._save()
            await self._notify_sessions("今日计划已更新")
            logger.info("[Planner] 今日计划已生成")
        except Exception as e:
            logger.exception(f"[Planner] 计划生成失败: {e}")

    async def run_afternoon_plan(self) -> None:
        logger.info("[Planner] 开始更新下午计划")
        try:
            existing_plan = self.get_plan()
            plan_json = (
                json.dumps([item.model_dump() for item in existing_plan], ensure_ascii=False, indent=2)
                if existing_plan
                else "无"
            )
            events_text = await self._gather_context(date.today().isoformat())
            notes_text = await self.moonlark_main.get_relevant_notes()
            messages = await get_messages(
                "planner_afternoon",
                plan=plan_json,
                events=events_text,
                notes=notes_text,
            )
            result = await fetch_json(messages, PlanResponse, identify="Planner - Afternoon", reasoning_effort="medium")
            self._plan = result.plan
            self._save()
            await self._notify_sessions("今日计划已更新")
            logger.info("[Planner] 下午计划已更新")
        except Exception as e:
            logger.exception(f"[Planner] 计划更新失败: {e}")

    def get_plan(self) -> Optional[list[PlanItem]]:
        if self._plan is not None:
            return self._plan
        path = _today_plan_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._plan = [PlanItem(**item) for item in data.get("plan", [])]
            return self._plan
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def get_plan_text(self) -> str:
        plan = self.get_plan()
        if not plan:
            return "今日暂无计划。"
        lines = []
        for item in plan:
            lines.append(f"[{item.period}] {item.content}")
        return "\n".join(lines)

    def _save(self) -> None:
        PLAN_DIR.mkdir(parents=True, exist_ok=True)
        path = _today_plan_path()
        data = {"plan": [item.model_dump() for item in self._plan]} if self._plan else {"plan": []}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def cleanup_expired_plans(max_age_days: int = MAX_PLAN_AGE_DAYS) -> int:
        """清理超过指定天数的过期计划文件"""
        count = 0
        today = date.today()
        if not PLAN_DIR.exists():
            return 0
        for filename in os.listdir(str(PLAN_DIR)):
            if not filename.startswith("plan_") or not filename.endswith(".json"):
                continue
            date_str = filename.removeprefix("plan_").removesuffix(".json")
            try:
                file_date = date.fromisoformat(date_str)
                if (today - file_date).days > max_age_days:
                    filepath = str(PLAN_DIR / filename)
                    os.remove(filepath)
                    count += 1
            except (ValueError, OSError):
                continue
        if count:
            logger.info(f"[Planner] 已清理 {count} 个过期计划文件")
        return count

    async def _gather_context(self, day: Optional[str] = None) -> str:
        from .event_collector import event_collector

        if day is None:
            day = (date.today() - timedelta(days=1)).isoformat()
        return await event_collector.get_all_events_summary(date=day)

    async def _notify_sessions(self, event_text: str) -> None:
        from ..session import groups

        for session in groups.values():
            try:
                await session.post_event(event_text, "none")
            except Exception as e:
                logger.warning(f"[Planner] 通知会话失败: {e}")
