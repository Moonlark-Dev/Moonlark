"""Jev (TypeSafe System One) 请求封装：构造问题、发起评估、解析类型化答案"""

import asyncio
from typing import Any, Optional

import httpx
from nonebot.log import logger
from pydantic import ValidationError

from ..config import config
from ..lang import lang
from ..types import Answer, ChoiceAnswer, InstructionsLike, LangRef, NoulAnswer, Question, ScoreAnswer, TextLike
from .client import client


class JevError(RuntimeError):
    """Jev 请求失败"""


class JevNotConfigured(JevError):
    """未配置 typesafe_api_key"""


async def resolve_text(value: TextLike, lang_str: str) -> str:
    """把 LangRef 解析成本地化文本，普通字符串原样返回"""
    if isinstance(value, LangRef):
        return await lang.text(value.key, lang_str, *value.args)
    return str(value)


async def _resolve_instructions(instructions: InstructionsLike, lang_str: str) -> Any:
    if isinstance(instructions, dict):
        return {key: await resolve_text(value, lang_str) for key, value in instructions.items()}
    return await resolve_text(instructions, lang_str)


async def _resolve_criteria(criteria: Any, lang_str: str) -> Any:
    if criteria is None:
        return None
    if isinstance(criteria, dict):
        return {str(key): await resolve_text(value, lang_str) for key, value in criteria.items()}
    if isinstance(criteria, list):
        return [await resolve_text(value, lang_str) for value in criteria]
    return await resolve_text(criteria, lang_str)


async def build_payload(
    state: Any,
    questions: dict[str, Question],
    lang_str: str,
    model: Optional[str] = None,
) -> dict:
    """构造 POST /systemone 的请求体（解析全部本地化文本）"""
    payload_questions: dict[str, dict] = {}
    for question_id, question in questions.items():
        entry: dict[str, Any] = {
            "type": question.type,
            "instructions": await _resolve_instructions(question.instructions, lang_str),
        }
        criteria = await _resolve_criteria(question.criteria, lang_str)
        if criteria is not None:
            entry["criteria"] = criteria
        payload_questions[question_id] = entry
    return {
        "state": state,
        "model": model or config.typesafe_model,
        "questions": payload_questions,
    }


def _parse_answer(question: Question, data: Any) -> Optional[Answer]:
    if not isinstance(data, dict):
        return None
    try:
        if question.type == "choice":
            if not isinstance(data.get("choice"), str):
                return None
            return ChoiceAnswer.model_validate(data)
        if question.type == "score":
            if not isinstance(data.get("score"), (int, float)):
                return None
            return ScoreAnswer.model_validate(data)
        if not isinstance(data.get("noul"), (int, float)):
            return None
        return NoulAnswer.model_validate(data)
    except ValidationError:
        return None


async def ask(
    state: Any,
    questions: dict[str, Question],
    *,
    lang_str: str = "zh_hans",
    identify: str = "Jev",
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict[str, Answer]:
    """向 Jev 提交一次评估

    Args:
        state: 被评估的状态，字符串或 JSON 可序列化的对象
        questions: 问题 ID -> :class:`Question`，答案按同样的 ID 返回
        lang_str: 会话语言（解析 :class:`LangRef` 时使用）
        identify: 调用方标识，仅用于日志
        model: 覆盖默认模型
        timeout: 覆盖默认超时（秒）

    Returns:
        问题 ID -> 类型化答案；无法解析的答案会被跳过并记录警告

    Raises:
        JevNotConfigured: 未配置 ``typesafe_api_key``
        JevError: 请求失败或返回结构异常
    """
    if not config.typesafe_api_key:
        raise JevNotConfigured("未配置 typesafe_api_key（TYPESAFE_API_KEY），无法调用 Jev")
    if not questions:
        return {}

    payload = await build_payload(state, questions, lang_str, model)
    request_kwargs: dict[str, Any] = {
        "json": payload,
        "headers": {"Authorization": f"Bearer {config.typesafe_api_key}"},
    }
    if timeout is not None:
        request_kwargs["timeout"] = timeout

    attempts = 1 + max(0, config.typesafe_max_retries)
    last_error: Optional[Exception] = None
    data: Any = None
    for attempt in range(1, attempts + 1):
        try:
            logger.debug(f"[Jev:{identify}] 请求模型 {payload['model']}（第 {attempt}/{attempts} 次）")
            response = await client.post("/systemone", **request_kwargs)
            response.raise_for_status()
            data = response.json()
            break
        except (httpx.HTTPError, ValueError) as e:
            last_error = e
            logger.warning(f"[Jev:{identify}] 请求失败（第 {attempt}/{attempts} 次）: {e}")
            if attempt < attempts:
                await asyncio.sleep(attempt)
    else:
        raise JevError(f"Jev 请求失败: {last_error}") from last_error

    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise JevError(f"Jev 返回缺少 answers 字段: {data!r}")
    raw_answers: dict = data["answers"]

    answers: dict[str, Answer] = {}
    for question_id, question in questions.items():
        parsed = _parse_answer(question, raw_answers.get(question_id))
        if parsed is None:
            logger.warning(f"[Jev:{identify}] 问题 {question_id} 未取得有效答案: {raw_answers.get(question_id)!r}")
        else:
            answers[question_id] = parsed
    return answers
