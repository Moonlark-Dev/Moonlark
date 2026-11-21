"""“缩略” 的数据结构：标签说明、生成题目结构与本地缓存文件格式。"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

KNOWN_TAG_DESCRIPTIONS: dict[str, str] = {
    "精选": "构思巧妙、断句误导极佳的代表作",
    "词源": "原词与答案更偏向词源演变关系而非现代简称",
    "别称": "原词与答案更偏向全称与日常别称关系",
    "多解": "题面较短，可能存在不止一种合理解法",
    "变格": "涉及拼音、罗马音或数字谐音层面的娱乐向拆解",
}


def _normalize_circles(text: str) -> str:
    return text.replace("〇", "○").replace("◯", "○")


class GeneratedQuestion(BaseModel):
    """模型生成的一道《缩略》谜题。"""

    full_word: str
    breakdown: str
    question: str
    answers: list[str]
    hint: list[str] = Field(default_factory=list)
    difficulty: int = 2
    tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("answers", mode="before")
    @classmethod
    def _validate_answers(cls, value: object) -> list[str]:
        if isinstance(value, str):
            raw_items: list[object] = [value]
        elif isinstance(value, list):
            raw_items = value
        else:
            raise TypeError("answers 必须为字符串或字符串列表")
        cleaned: list[str] = []
        for item in raw_items:
            if not isinstance(item, str):
                raise TypeError("answers 中的每一项都必须为字符串")
            stripped = item.strip()
            if stripped:
                cleaned.append(stripped)
        return cleaned

    @field_validator("hint", mode="before")
    @classmethod
    def _validate_hint(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_parts = re.split(r"[;；]", value)
        elif isinstance(value, list):
            raw_parts = []
            for item in value:
                if not isinstance(item, str):
                    raise TypeError("hint 中的每一项都必须为字符串")
                raw_parts.append(item)
        else:
            raise TypeError("hint 必须为字符串、字符串列表或 None")
        cleaned: list[str] = []
        for part in raw_parts:
            normalized = _normalize_circles(part).strip()
            if normalized:
                cleaned.append(normalized)
        return cleaned

    @field_validator("tags", mode="before")
    @classmethod
    def _validate_tags(cls, value: object) -> dict[str, str]:
        if value is None:
            return {}
        result: dict[str, str] = {}
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    raise TypeError("tags 列表中的每一项都必须为字符串")
                key = item.strip()
                if key in KNOWN_TAG_DESCRIPTIONS:
                    result[key] = KNOWN_TAG_DESCRIPTIONS[key]
            return result
        if isinstance(value, dict):
            for raw_key, raw_desc in value.items():
                if not isinstance(raw_key, str):
                    raise TypeError("tags 的键必须为字符串")
                if raw_desc is not None and not isinstance(raw_desc, str):
                    raise TypeError("tags 的值必须为字符串或 None")
                key = raw_key.strip()
                if not key or key not in KNOWN_TAG_DESCRIPTIONS:
                    continue
                desc = raw_desc.strip() if isinstance(raw_desc, str) else ""
                result[key] = desc or KNOWN_TAG_DESCRIPTIONS[key]
            return result
        raise TypeError("tags 必须为字典、列表或 None")

    @property
    def primary_answer(self) -> str:
        """返回首个标准答案；若答案列表为空则返回空字符串。"""
        return self.answers[0].strip() if self.answers else ""


class QuestionStoreData(BaseModel):
    """本地缓存文件：待玩题目 + 近期出过的原词、答案与题面（用于去重）。"""

    questions: list[GeneratedQuestion] = Field(default_factory=list)
    recent_full_words: list[str] = Field(default_factory=list)
    recent_answers: list[str] = Field(default_factory=list)
    recent_questions: list[str] = Field(default_factory=list)
