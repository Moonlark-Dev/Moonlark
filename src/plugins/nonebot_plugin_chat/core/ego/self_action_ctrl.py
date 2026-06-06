"""自主活动控制器

按设计文档实现：
- 管理当前正在进行的自主活动（如"学习CSS"、"做拉伸"）
- 提供活动计时和自动结束功能
- 维护活动历史记录
- duration 由单独请求 LLM 生成
- 通过 Runner 模式执行不同类型的活动（查找、学习等）
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_openai import MessageFetcher
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import generate_message

from ...lang import lang
from ...models import SelfActionDurationResponse, TaskClassificationResponse
from ...utils.prompt import get_prompt_text
from ...utils.tool_manager import ToolManager

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain


class ActionType(Enum):
    LEARN = "学习"
    TASK = "任务"


class SelfActionAgent:
    """自主活动 AI Agent

    类似 AskAISession，使用 ToolManager 提供的 agent 工具列表执行任务。
    """

    def __init__(self, lang_str: str) -> None:
        self.lang_str = lang_str
        self.tool_manager = ToolManager(lang_str=lang_str)
        self.functions = []

    async def setup(self) -> None:
        self.functions = await self.tool_manager.select_tools("agent")

    async def execute_task(self, activity: str) -> str:
        if not self.functions:
            await self.setup()

        system_text = await lang.text(
            "self_action.agent.system",
            self.lang_str,
            datetime.now().isoformat(),
        )
        user_text = activity

        fetcher = await MessageFetcher.create(
            [
                generate_message(system_text, "system"),
                generate_message(user_text, "user"),
            ],
            False,
            functions=self.functions,
            identify="SelfActionAgent",
        )
        return await fetcher.fetch_last_message()


class SelfActionController:
    """自主活动控制器

    按设计文档属性：
    - current_activity: Optional[str]
    - activity_start_time: Optional[datetime]
    - activity_history: list
    """

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self.current_activity: Optional[str] = None
        self.activity_start_time: Optional[datetime] = None
        self.activity_history: list[dict] = []
        self.lang = moonlark_main.lang_str
        self.agent = SelfActionAgent(self.lang)
        self._task: Optional[asyncio.Task] = None

    def get_status(self) -> dict:
        return {
            "current_activity": self.current_activity,
            "activity_start_time": self.activity_start_time.isoformat() if self.activity_start_time else None,
        }

    async def start_action(self, activity: str) -> str:
        if self.current_activity:
            return f"当前正在「{self.current_activity}」，无法同时进行其他活动。"

        self.current_activity = activity
        self.activity_start_time = datetime.now()
        return await self._run_action(activity)

    async def _run_action(self, activity: str) -> str:
        try:
            task_type = await self.get_task_type(activity)
            if task_type == ActionType.LEARN:
                result = await self.agent.execute_task(activity)
            else:
                duration = await self.get_task_duration(activity)
                await asyncio.sleep(duration * 60)
                result = None

            self.activity_history.append(
                {
                    "activity": activity,
                    "start_time": self.activity_start_time.isoformat() if self.activity_start_time else None,
                    "end_time": datetime.now().isoformat(),
                    "result": result,
                }
            )
            logger.info(f"[SelfAction] 活动完成: {activity}")
            return result or f"活动完成: {activity}"
        except asyncio.CancelledError:
            return f"[SelfAction] 活动取消: {activity}"
        except Exception as e:
            return f"[SelfAction] 活动失败: {e}"
        finally:
            self.current_activity = None
            self.activity_start_time = None
            self._task = None

    async def get_task_duration(self, activity: str) -> int:
        identity_prompt = await get_prompt_text("identity")
        response = await fetch_json(
            [
                generate_message(await lang.text("self_action.duration.system", self.lang, identity_prompt), "system"),
                generate_message(await lang.text("self_action.duration.user", self.lang, activity), "user"),
            ],
            SelfActionDurationResponse,
            identify="SelfAction - Duration Assessment",
        )
        return response.duration_minutes

    async def get_task_type(self, activity: str) -> ActionType:
        identity_prompt = await get_prompt_text("identity")
        response = await fetch_json(
            [
                generate_message(
                    await lang.text("moonlark_main.task_classification.prompt", self.lang, identity_prompt),
                    "system",
                ),
                generate_message(
                    await lang.text("moonlark_main.task_classification.user", self.lang, activity),
                    "user",
                ),
            ],
            TaskClassificationResponse,
            identify="SelfAction - Task Classification",
        )
        return ActionType(response.activity_type)
