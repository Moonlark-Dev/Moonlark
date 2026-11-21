from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator


class Config(BaseModel):
    """Plugin Config Here"""

    language_dir: str = "src/lang"
    command_start: list[str] = ["/"]
    # 填充本地化文本中 {__prefix__} 的指令前缀（环境变量 COMMAND_PREFIX）。
    # 必须是 COMMAND_START 中的一个前缀，且只能设置一个；留空时使用 COMMAND_START 的第一个前缀。
    command_prefix: Optional[str] = None

    @field_validator("command_prefix", mode="before")
    @classmethod
    def _normalize_command_prefix(cls, value: Any) -> Any:
        """空字符串视为未设置"""
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _validate_command_prefix(self) -> "Config":
        """COMMAND_PREFIX 必须属于 COMMAND_START"""
        if self.command_prefix is not None and self.command_prefix not in self.command_start:
            raise ValueError(
                f"COMMAND_PREFIX（{self.command_prefix!r}）必须是 COMMAND_START（{self.command_start!r}）中的一个前缀",
            )
        return self
