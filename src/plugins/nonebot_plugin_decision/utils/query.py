"""OpenRouter Decisions API 请求封装：构造问题、发起评估、解析类型化答案"""

import asyncio
import json
from typing import Any, Optional

import httpx
from nonebot.log import logger
from pydantic import ValidationError

from ..config import config
from ..lang import lang
from ..types import (
    Answer,
    BoxAnswer,
    ChoiceAnswer,
    LangRef,
    NoulAnswer,
    Question,
    ScoreAnswer,
    TextLike,
)
from .client import client

# OpenRouter Decisions API 支持的多模态输入块类型
_MEDIA_PART_TYPES = frozenset({"image_url", "input_audio", "video_url", "file", "text"})
# OpenRouter Decisions API 的 session_id 最大长度限制
_MAX_SESSION_ID_LENGTH = 256
# 仅在这些 HTTP 状态码下才允许重试（其余 4xx 属于客户端参数/鉴权/安全拦截问题，重试无意义）
_RETRYABLE_STATUS_CODES = frozenset({408, 429})


class DecisionError(RuntimeError):
    """Decisions API 请求失败"""


class DecisionNotConfiguredError(DecisionError):
    """未配置 decision_api_key"""


def resolve_endpoint(base_url: str) -> str:
    """根据 ``base_url`` 解析最终请求路径

    - ``https://openrouter.ai/api/alpha`` -> ``/decisions``
    - ``https://openrouter.ai/api/alpha/decisions`` -> 完整 URL 原样请求（避免多余斜杠）
    - ``https://api.typesafe.ai/v1`` -> ``/systemone``（兼容原生 TypeSafe 地址）
    """
    normalized = base_url.rstrip("/")
    if normalized.endswith(("/decisions", "/systemone")):
        return normalized
    if normalized.endswith("typesafe.ai/v1"):
        return "/systemone"
    return "/decisions"


def _is_retryable_status(status_code: int) -> bool:
    return status_code >= 500 or status_code in _RETRYABLE_STATUS_CODES


def _is_empty_state(state: Any) -> bool:
    if state is None:
        return True
    if isinstance(state, str):
        return not state.strip()
    if isinstance(state, list):
        return len(state) == 0
    return False


async def resolve_text(value: TextLike, lang_str: str) -> str:
    """把 LangRef 解析成本地化文本，普通字符串原样返回"""
    if isinstance(value, LangRef):
        return await lang.text(value.key, lang_str, *value.args)
    return str(value)


async def _normalize_state(state: Any, lang_str: str) -> Any:
    """把调用方传入的 state 规范化为 OpenRouter Decisions API 接受的 string 或多模态 list

    OpenRouter Decisions API（尤其 ``google/gemini-decision-1``）要求 ``state`` 为非空字符串
    或由文本/媒体块组成的数组；若调用方直接传入业务字典（如 ``{"history_events": ...}``），
    统一序列化为格式化 JSON 字符串，保证所有模型均可正常读取结构化字段。
    """
    if isinstance(state, LangRef):
        return await resolve_text(state, lang_str)
    if isinstance(state, str):
        return state
    if isinstance(state, list):
        normalized_items: list[Any] = []
        for item in state:
            if isinstance(item, LangRef):
                normalized_items.append(await resolve_text(item, lang_str))
            elif isinstance(item, dict) and item.get("type") not in _MEDIA_PART_TYPES:
                normalized_items.append(json.dumps(item, ensure_ascii=False, indent=2))
            else:
                normalized_items.append(item)
        return normalized_items
    if isinstance(state, dict):
        if state.get("type") in _MEDIA_PART_TYPES:
            return [state]
        return json.dumps(state, ensure_ascii=False, indent=2)
    return str(state)


async def _resolve_criteria(criteria: Any, lang_str: str) -> Any:
    if criteria is None:
        return None
    if isinstance(criteria, dict):
        return {
            str(key): (None if value is None else await resolve_text(value, lang_str))
            for key, value in criteria.items()
        }
    if isinstance(criteria, list):
        return [await resolve_text(value, lang_str) for value in criteria]
    return await resolve_text(criteria, lang_str)


async def build_payload(
    state: Any,
    questions: dict[str, Question],
    lang_str: str,
    model: Optional[str] = None,
    *,
    assets: Optional[dict[str, Any]] = None,
    provider: Optional[dict[str, Any]] = None,
    session_id: Optional[str] = None,
    user: Optional[str] = None,
    trace: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """构造 POST /decisions 的请求体（解析全部本地化文本并规范化 state）"""
    payload_questions: dict[str, dict[str, Any]] = {}
    for question_id, question in questions.items():
        entry: dict[str, Any] = {
            "type": question.type,
            "instructions": await resolve_text(question.instructions, lang_str),
        }
        criteria = await _resolve_criteria(question.criteria, lang_str)
        if criteria is not None:
            entry["criteria"] = criteria
        payload_questions[question_id] = entry

    payload: dict[str, Any] = {
        "state": await _normalize_state(state, lang_str),
        "model": model or config.decision_model,
        "questions": payload_questions,
    }
    if assets is not None:
        payload["assets"] = assets
    if provider is not None:
        payload["provider"] = provider
    if session_id:
        payload["session_id"] = session_id[:_MAX_SESSION_ID_LENGTH]
    if user:
        payload["user"] = user
    if trace is not None:
        payload["trace"] = trace
    return payload


def _parse_answer(question: Question, data: Any) -> tuple[Optional[Answer], bool]:
    """解析单个问题的答案，返回 ``(答案或 None, 是否为模型明确拒绝 refusal)``"""
    if not isinstance(data, dict):
        return None, False
    if data.get("type") == "refusal":
        return None, True
    try:
        if question.type == "choice":
            if not isinstance(data.get("choice"), str):
                return None, False
            return ChoiceAnswer.model_validate(data), False
        if question.type == "score":
            if not isinstance(data.get("score"), (int, float)):
                return None, False
            return ScoreAnswer.model_validate(data), False
        if question.type == "box":
            if not isinstance(data.get("box"), dict):
                return None, False
            return BoxAnswer.model_validate(data), False
        if not isinstance(data.get("noul"), (int, float)):
            return None, False
        return NoulAnswer.model_validate(data), False
    except ValidationError:
        return None, False


async def ask(
    state: Any,
    questions: dict[str, Question],
    *,
    lang_str: str = "zh_hans",
    identify: str = "Decision",
    model: Optional[str] = None,
    request_timeout: Optional[float] = None,
    assets: Optional[dict[str, Any]] = None,
    provider: Optional[dict[str, Any]] = None,
    session_id: Optional[str] = None,
    user: Optional[str] = None,
    trace: Optional[dict[str, Any]] = None,
) -> dict[str, Answer]:
    """向 OpenRouter Decisions API 提交一次类型化决策请求

    Args:
        state: 被评估的状态，支持字符串、可 JSON 序列化的字典或多模态内容块列表
        questions: 问题 ID -> :class:`Question`，答案按同样的 ID 返回
        lang_str: 会话语言（解析 :class:`LangRef` 时使用）
        identify: 调用方标识，仅用于日志
        model: 覆盖默认模型
        request_timeout: 覆盖默认超时（秒）
        assets: OpenRouter Decisions API 的可复用命名资源映射
        provider: OpenRouter Provider 路由偏好配置
        session_id: 会话分组标识（超过 256 字符会自动截断）
        user: 终端用户标识
        trace: 追踪元数据

    Returns:
        问题 ID -> 类型化答案；被模型拒绝（refusal）或无法解析的答案会被跳过

    Raises:
        DecisionNotConfiguredError: 未配置 ``decision_api_key``
        DecisionError: 请求参数为空、HTTP 请求失败或返回结构异常
    """
    if not config.decision_api_key:
        raise DecisionNotConfiguredError("未配置 decision_api_key（DECISION_API_KEY），无法调用 Decisions API")
    if not questions:
        return {}

    payload = await build_payload(
        state,
        questions,
        lang_str,
        model,
        assets=assets,
        provider=provider,
        session_id=session_id,
        user=user,
        trace=trace,
    )
    if _is_empty_state(payload["state"]) and not assets:
        raise DecisionError("Decisions API 的 state 不能为空")

    endpoint = resolve_endpoint(config.decision_base_url)
    request_kwargs: dict[str, Any] = {
        "json": payload,
        "headers": {"Authorization": f"Bearer {config.decision_api_key}"},
    }
    if request_timeout is not None:
        request_kwargs["timeout"] = request_timeout

    attempts = 1 + max(0, config.decision_max_retries)
    last_error_msg = ""
    last_error: Optional[Exception] = None
    data: Any = None
    for attempt in range(1, attempts + 1):
        try:
            logger.debug(f"[Decision:{identify}] 请求模型 {payload['model']}（第 {attempt}/{attempts} 次）")
            response = await client.post(endpoint, **request_kwargs)
            response.raise_for_status()
            data = response.json()
            break
        except httpx.HTTPStatusError as e:
            last_error = e
            status_code = e.response.status_code
            body_preview = e.response.text.strip()[:500]
            detail = f"HTTP {status_code}: {body_preview}" if body_preview else f"HTTP {status_code}: {e}"
            last_error_msg = detail
            logger.warning(f"[Decision:{identify}] 请求失败（第 {attempt}/{attempts} 次）: {detail}")
            if not _is_retryable_status(status_code):
                break
            if attempt < attempts:
                await asyncio.sleep(attempt)
        except (httpx.HTTPError, ValueError) as e:
            last_error = e
            last_error_msg = str(e)
            logger.warning(f"[Decision:{identify}] 请求失败（第 {attempt}/{attempts} 次）: {e}")
            if attempt < attempts:
                await asyncio.sleep(attempt)
    else:
        raise DecisionError(f"Decisions API 请求失败: {last_error_msg}") from last_error

    if data is None:
        raise DecisionError(f"Decisions API 请求失败: {last_error_msg}") from last_error

    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise DecisionError(f"Decisions API 返回缺少 answers 字段: {data!r}")
    raw_answers: dict[str, Any] = data["answers"]

    answers: dict[str, Answer] = {}
    for question_id, question in questions.items():
        raw_answer = raw_answers.get(question_id)
        parsed, refused = _parse_answer(question, raw_answer)
        if refused:
            logger.info(f"[Decision:{identify}] 问题 {question_id} 被模型拒绝回答 (refusal)")
        elif parsed is None:
            logger.warning(f"[Decision:{identify}] 问题 {question_id} 未取得有效答案: {raw_answer!r}")
        else:
            answers[question_id] = parsed
    return answers
