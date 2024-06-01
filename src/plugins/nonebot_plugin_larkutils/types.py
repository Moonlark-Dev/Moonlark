from typing import Literal, Optional, TypedDict


class ReviewResult(TypedDict):
    conclusion: Literal["合规", "疑似", "不合规", "出错"]
    message: Optional[str]
    compliance: bool
