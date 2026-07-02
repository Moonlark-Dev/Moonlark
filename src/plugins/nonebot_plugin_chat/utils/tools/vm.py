#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

"""
VM 远程执行工具模块

提供与 moonlark-vm 服务交互的工具函数，用于在远程 Docker 容器中执行命令。
"""

import httpx
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from nonebot import get_driver
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

from ...config import config
from ...types import GetTextFunc

# 输出截断长度限制
OUTPUT_MAX_LENGTH = 4000


@dataclass
class VMStatusCache:
    """VM 服务状态缓存"""

    available: bool = False
    container_id: str = ""
    container_status: str = ""
    last_check_time: Optional[datetime] = None
    error_message: str = ""


# 全局状态缓存
_vm_status_cache = VMStatusCache()


def _get_headers() -> dict:
    """获取请求头"""
    return {
        "Authorization": f"Bearer {config.vm_api_token}",
        "Content-Type": "application/json",
    }


def _get_base_url() -> str:
    """获取 API 基础 URL"""
    url = config.vm_api_url.rstrip("/")
    return url


async def _check_vm_status() -> None:
    """检查 VM 服务状态并更新缓存"""
    global _vm_status_cache

    if not config.vm_api_url or not config.vm_api_token:
        _vm_status_cache.available = False
        _vm_status_cache.error_message = "VM 服务未配置"
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_get_base_url()}/")
            if response.status_code == 200:
                data = response.json()
                _vm_status_cache.available = True
                _vm_status_cache.container_id = data.get("container_id", "")
                _vm_status_cache.container_status = data.get("container_status", "")
                _vm_status_cache.error_message = ""
                _vm_status_cache.last_check_time = datetime.now()
                logger.debug(f"VM 服务状态检查成功: {data}")
            else:
                _vm_status_cache.available = False
                _vm_status_cache.error_message = f"服务返回错误状态码: {response.status_code}"
    except httpx.ConnectError:
        _vm_status_cache.available = False
        _vm_status_cache.error_message = "无法连接到 VM 服务"
    except httpx.TimeoutException:
        _vm_status_cache.available = False
        _vm_status_cache.error_message = "连接 VM 服务超时"
    except Exception as e:
        _vm_status_cache.available = False
        _vm_status_cache.error_message = f"检查服务状态时发生错误: {str(e)}"
        logger.exception(e)

    _vm_status_cache.last_check_time = datetime.now()


def is_vm_configured() -> bool:
    """检查 VM 是否已配置"""
    return bool(config.vm_api_url and config.vm_api_token)


def is_vm_available() -> bool:
    """检查 VM 服务是否可用"""
    return _vm_status_cache.available


def _truncate_output(output: str) -> tuple[str, bool]:
    """
    截断输出内容

    Args:
        output: 原始输出

    Returns:
        (截断后的输出, 是否发生截断)
    """
    if len(output) <= OUTPUT_MAX_LENGTH:
        return output, False
    return output[-OUTPUT_MAX_LENGTH:], True


def _format_datetime(dt_str: Optional[str]) -> str:
    """格式化日期时间字符串"""
    if not dt_str:
        return "未知"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return dt_str


def _get_status_emoji(status: str) -> str:
    """获取状态对应的 emoji"""
    status_emojis = {
        "pending": "⏳",
        "running": "🔄",
        "completed": "✅",
        "failed": "❌",
        "stopped": "🛑",
    }
    return status_emojis.get(status, "❓")


async def vm_create_task(command: str, title: str, get_text: GetTextFunc) -> str:
    """
    在远程 Docker 容器中创建一个命令执行任务

    Args:
        command: 要执行的 Shell 命令
        title: 任务标题
        get_text: 获取本地化文本的函数

    Returns:
        任务创建结果
    """
    if not is_vm_available():
        return await get_text("vm.unavailable", _vm_status_cache.error_message)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_get_base_url()}/create",
                headers=_get_headers(),
                json={"command": command, "title": title},
            )

            if response.status_code == 200:
                data = response.json()
                task_id = data.get("task_id", "未知")
                return await get_text("vm.create_task.success", task_id, title, command)
            else:
                return await get_text("vm.create_task.failed", response.status_code, response.text)

    except httpx.TimeoutException:
        return await get_text("vm.create_task.timeout")
    except Exception as e:
        logger.exception(e)
        return await get_text("vm.create_task.error", str(e))


async def vm_get_task_state(task_id: str, get_text: GetTextFunc) -> str:
    """
    获取任务的执行状态和输出

    Args:
        task_id: 任务 ID
        get_text: 获取本地化文本的函数

    Returns:
        任务状态信息
    """
    if not is_vm_available():
        return await get_text("vm.unavailable", _vm_status_cache.error_message)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_get_base_url()}/tasks/{task_id}",
                headers=_get_headers(),
            )

            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                status_emoji = _get_status_emoji(status)

                result_lines = [
                    await get_text("vm.get_task_state.status_header"),
                    await get_text("vm.get_task_state.task_id", data.get("id", task_id)),
                    await get_text("vm.get_task_state.title", data.get("title", "未知")),
                    await get_text("vm.get_task_state.status", status, status_emoji),
                ]

                if data.get("exit_code") is not None:
                    result_lines.append(await get_text("vm.get_task_state.exit_code", data["exit_code"]))

                result_lines.append(
                    await get_text("vm.get_task_state.created_at", _format_datetime(data.get("created_at")))
                )

                if data.get("started_at"):
                    result_lines.append(
                        await get_text("vm.get_task_state.started_at", _format_datetime(data["started_at"]))
                    )

                if data.get("finished_at"):
                    result_lines.append(
                        await get_text("vm.get_task_state.finished_at", _format_datetime(data["finished_at"]))
                    )

                # 处理输出
                output = data.get("output", "")
                if output:
                    truncated_output, was_truncated = _truncate_output(output)
                    result_lines.append("")
                    result_lines.append(await get_text("vm.get_task_state.output_header"))
                    result_lines.append(truncated_output)
                    if was_truncated:
                        result_lines.append("")
                        result_lines.append(await get_text("vm.get_task_state.output_truncated", OUTPUT_MAX_LENGTH))
                else:
                    result_lines.append("")
                    result_lines.append(await get_text("vm.get_task_state.output_none"))

                return "\n".join(result_lines)

            elif response.status_code == 404:
                return await get_text("vm.get_task_state.not_found", task_id)
            else:
                return await get_text("vm.get_task_state.failed", response.status_code, response.text)

    except httpx.TimeoutException:
        return await get_text("vm.get_task_state.timeout")
    except Exception as e:
        logger.exception(e)
        return await get_text("vm.get_task_state.error", str(e))


async def vm_send_input(task_id: str, input_text: str, get_text: GetTextFunc) -> str:
    """
    向正在运行的任务发送输入

    Args:
        task_id: 任务 ID
        input_text: 要发送的输入内容
        get_text: 获取本地化文本的函数

    Returns:
        发送结果
    """
    if not is_vm_available():
        return await get_text("vm.unavailable", _vm_status_cache.error_message)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_get_base_url()}/tasks/{task_id}",
                headers=_get_headers(),
                json={"input": input_text},
            )

            if response.status_code == 200:
                # 截断显示的输入内容，避免太长
                display_input = input_text[:100] + "..." if len(input_text) > 100 else input_text
                display_input = display_input.replace("\n", "\\n")
                return await get_text("vm.send_input.success", task_id, display_input)

            elif response.status_code == 404:
                return await get_text("vm.send_input.not_found", task_id)
            elif response.status_code == 400:
                return await get_text("vm.send_input.not_running", task_id)
            else:
                return await get_text("vm.send_input.failed", response.status_code, response.text)

    except httpx.TimeoutException:
        return await get_text("vm.send_input.timeout")
    except Exception as e:
        logger.exception(e)
        return await get_text("vm.send_input.error", str(e))


async def vm_stop_task(task_id: str, get_text: GetTextFunc) -> str:
    """
    停止正在运行的任务

    Args:
        task_id: 任务 ID
        get_text: 获取本地化文本的函数

    Returns:
        停止结果
    """
    if not is_vm_available():
        return await get_text("vm.unavailable", _vm_status_cache.error_message)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{_get_base_url()}/tasks/{task_id}",
                headers=_get_headers(),
            )

            if response.status_code == 200:
                return await get_text("vm.stop_task.success", task_id)

            elif response.status_code == 404:
                return await get_text("vm.stop_task.not_found", task_id)
            else:
                return await get_text("vm.stop_task.failed", response.status_code, response.text)

    except httpx.TimeoutException:
        return await get_text("vm.stop_task.timeout")
    except Exception as e:
        logger.exception(e)
        return await get_text("vm.stop_task.error", str(e))


# 注册定时任务检查 VM 状态
if is_vm_configured():

    @scheduler.scheduled_job("interval", seconds=60, id="check_vm_status")
    async def _scheduled_vm_check() -> None:
        """定时检查 VM 服务状态"""
        await _check_vm_status()

    @get_driver().on_startup
    async def _initial_vm_check() -> None:
        """启动时的初始 VM 状态检查"""
        await _check_vm_status()
        if _vm_status_cache.available:
            logger.info(
                f"VM 服务已连接: container_id={_vm_status_cache.container_id}, "
                f"status={_vm_status_cache.container_status}"
            )
        else:
            logger.warning(f"VM 服务不可用: {_vm_status_cache.error_message}")
