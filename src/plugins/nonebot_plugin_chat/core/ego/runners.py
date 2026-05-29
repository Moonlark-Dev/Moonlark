"""自主活动 Runner 模式

每个 Runner 负责一类活动的执行逻辑。
- SearchRunner: 查找类活动，执行 web_search，结果存入 note
- DefaultRunner: 普通活动，只计时
"""

import re
from abc import ABC, abstractmethod
from typing import Optional

from nonebot import logger

# 查找类活动关键词
_SEARCH_KEYWORDS = re.compile(
    r"查找|搜索|查一下|搜一下|了解一下|看看|查查|搜搜|search|look\s*up",
    re.IGNORECASE,
)


class ActivityRunner(ABC):
    """活动 Runner 基类"""

    @abstractmethod
    def match(self, activity: str) -> bool:
        """判断是否匹配此 runner"""

    @abstractmethod
    async def run(self, activity: str, context_id: str = "self_action") -> Optional[str]:
        """执行活动，返回结果文本（可存入 note），无结果返回 None"""


class SearchRunner(ActivityRunner):
    """查找类活动 Runner

    匹配"查找/搜索/了解一下"等关键词，执行 web_search，
    结果存入 note_manager，供后续决策和博客使用。
    """

    def match(self, activity: str) -> bool:
        return bool(_SEARCH_KEYWORDS.search(activity))

    async def run(self, activity: str, context_id: str = "self_action") -> Optional[str]:
        try:
            from ...utils.tools.search import web_search
            from ...utils.note_manager import get_context_notes
            from ...lang import lang as lang_mod

            # 提取搜索关键词（去掉动词前缀）
            query = _SEARCH_KEYWORDS.sub("", activity).strip()
            if not query:
                query = activity

            # 执行搜索
            get_text = lambda key, *args: lang_mod.text(key, "zh_hans", *args)
            result = await web_search(query, get_text)

            if result and not result.startswith("搜索失败") and not result.startswith("未找到"):
                # 存入 note（7天过期）
                note_mgr = await get_context_notes(context_id)
                await note_mgr.create_note(
                    content=f"[查找] {activity}\n\n{result}",
                    keywords=query,
                    expire_hours=168,
                )
                logger.info(f"[SearchRunner] 搜索完成并存入 note: {query}，结果长度: {len(result)}")
            else:
                logger.info(f"[SearchRunner] 搜索无结果或失败: {query}")

            return result

        except Exception as e:
            logger.exception(f"[SearchRunner] 搜索失败: {e}")
            return f"搜索失败: {e}"


class DefaultRunner(ActivityRunner):
    """默认 Runner：普通活动，只计时，不执行额外操作"""

    def match(self, activity: str) -> bool:
        return True  # 兜底

    async def run(self, activity: str, context_id: str = "self_action") -> Optional[str]:
        return None


# Runner 列表（按优先级排列，先匹配的先执行）
RUNNERS: list[ActivityRunner] = [
    SearchRunner(),
    DefaultRunner(),
]


def get_runner(activity: str) -> ActivityRunner:
    """根据活动描述获取对应的 runner"""
    for runner in RUNNERS:
        if runner.match(activity):
            return runner
    return DefaultRunner()
