"""SQL 相关的通用工具."""

import asyncio
from typing import Awaitable, Callable, TypeVar

from nonebot.log import logger
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.sql import func
from sqlalchemy.sql._typing import ColumnExpressionArgument

T = TypeVar("T")

# MySQL / MariaDB 在 REPEATABLE READ 隔离级别下「先读后写」同一行时，如果该行在事务
# 期间被其它事务更新，会返回 1020 (ER_CHECKREAD，"Record has changed since last read
# in table")；1205（锁等待超时）与 1213（死锁）同样属于重开事务即可解决的瞬时冲突。
_RETRYABLE_MYSQL_ERROR_CODES = frozenset({1020, 1205, 1213})
# 并发首次写入同一主键时的重复键错误：MySQL 1062，MariaDB 1062 / 1555 / 2067
_DUPLICATE_KEY_ERROR_CODES = frozenset({1062, 1555, 2067})


def _error_args(error: BaseException) -> tuple[object, ...]:
    args = getattr(getattr(error, "orig", error), "args", ())
    return args if isinstance(args, tuple) else ()


def is_retryable_db_conflict(error: BaseException) -> bool:
    """判断异常是否属于可以通过重开事务重试的并发冲突."""
    args = _error_args(error)
    if not args:
        return False
    code = args[0]
    if isinstance(error, IntegrityError):
        if isinstance(code, int):
            return code in _DUPLICATE_KEY_ERROR_CODES
        return isinstance(code, str) and "unique constraint failed" in code.lower()
    if isinstance(error, OperationalError):
        if isinstance(code, int):
            return code in _RETRYABLE_MYSQL_ERROR_CODES
        return isinstance(code, str) and "database is locked" in code.lower()
    return False


async def retry_on_db_conflict(
    operation: Callable[[], Awaitable[T]],
    times: int = 3,
    delay: float = 0.05,
) -> T:
    """执行数据库操作，遇到并发冲突时重开事务重试.

    传入的 operation 每次都应使用全新的 session：冲突后原事务已经无法继续使用。
    """
    for attempt in range(1, times + 1):
        try:
            return await operation()
        except (IntegrityError, OperationalError) as error:
            if attempt >= times or not is_retryable_db_conflict(error):
                raise
            logger.warning(
                "数据库并发冲突，正在重试 (%s/%s): %s",
                attempt,
                times - 1,
                getattr(error, "orig", error),
            )
            await asyncio.sleep(delay * attempt)
    raise RuntimeError("unreachable")


async def get_id(session: async_scoped_session, col: ColumnExpressionArgument[int]) -> int:
    result = await session.scalar(select(func.max(col)))
    return (result + 1) if result is not None else 0
