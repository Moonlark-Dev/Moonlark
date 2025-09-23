#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################
import inspect
from contextlib import AsyncExitStack
from datetime import datetime

from exceptiongroup import catch
from nonebot.exception import StopPropagation, SkippedException, FinishedException, RejectedException, PausedException
from nonebot.internal.matcher import current_handler
from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot.adapters import Bot, Event
from typing import Optional, Any, Literal
from nonebot.params import T_State
from nonebot.typing import T_DependencyCache
from nonebot.utils import flatten_exception_group

from nonebot_plugin_larklang.__main__ import get_module_name
from nonebot_plugin_status_report.types import HandlerInfo, RunResult


def generator_run_result(func: Any, result: Literal["success", "skipped", "failed"], message: str) -> RunResult:
    return RunResult(
        result=result,
        message=message,
        handler=HandlerInfo(
            lineno=inspect.getsourcelines(func)[1],
            filename=inspect.getfile(func),
            name=func.__name__,
            plugin=get_module_name(inspect.getmodule(func)),
        ),
        timestamp=int(datetime.now().timestamp()),
    )


async def simple_run(
    self: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
    stack: Optional[AsyncExitStack] = None,
    dependency_cache: Optional[T_DependencyCache] = None,
) -> Any:
    logger.trace(f"{self} run with incoming args: " f"bot={bot}, event={event!r}, state={state!r}")

    def _handle_stop_propagation(exc_group: BaseExceptionGroup[StopPropagation]):
        self.block = True

    with self.ensure_context(bot, event):
        try:
            with catch({StopPropagation: _handle_stop_propagation}):
                # Refresh preprocess state
                self.state.update(state)

                while self.remain_handlers:
                    handler = self.remain_handlers.pop(0)
                    current_handler.set(handler)
                    logger.debug(f"Running handler {handler}")

                    def _handle_skipped(
                        exc_group: BaseExceptionGroup[SkippedException],
                    ):
                        reasons = [e for e in flatten_exception_group(exc_group)]
                        logger.debug(f"Handler {handler} skipped (due to {reasons})")
                        state["handler_results"].append(generator_run_result(handler.call, "skipped", str(reasons)))

                    with catch({SkippedException: _handle_skipped}):
                        await handler(
                            matcher=self,
                            bot=bot,
                            event=event,
                            state=self.state,
                            stack=stack,
                            dependency_cache=dependency_cache,
                        )
        except (FinishedException, RejectedException, PausedException) as e:
            if "handler" in locals():
                state["handler_results"].append(generator_run_result(handler.call, "success", type(e).__name__[:-9]))
            raise e
        except Exception as e:
            if "handler" in locals():
                state["handler_results"].append(generator_run_result(handler.call, "failed", str(e)))
            raise e
        finally:
            logger.info(f"{self} running complete")
        if "handler" in locals():
            state["handler_results"].append(generator_run_result(handler.call, "success", ""))
