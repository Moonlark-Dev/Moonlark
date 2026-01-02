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

"""
VM 远程执行工具模块

提供与 moonlark-vm 服务交互的工具函数，用于在远程 Docker 容器中执行命令。
"""

import httpx
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

from ...config import config
from ...lang import lang


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


async def vm_create_task(command: str, title: str) -> str:
    """
    在远程 Docker 容器中创建一个命令执行任务

    Args:
        command: 要执行的 Shell 命令
        title: 任务标题

    Returns:
        任务创建结果
    """
    if not is_vm_available():
        return f"❌ VM 服务当前不可用\n原因: {_vm_status_cache.error_message}"

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
                return f"""✅ 任务创建成功！
任务ID: {task_id}
标题: {title}
命令: {command}"""
            else:
                return f"❌ 任务创建失败\n状态码: {response.status_code}\n响应: {response.text}"

    except httpx.TimeoutException:
        return "❌ 请求超时，无法创建任务"
    except Exception as e:
        logger.exception(e)
        return f"❌ 创建任务时发生错误: {str(e)}"


async def vm_get_task_state(task_id: str) -> str:
    """
    获取任务的执行状态和输出

    Args:
        task_id: 任务 ID

    Returns:
        任务状态信息
    """
    if not is_vm_available():
        return f"❌ VM 服务当前不可用\n原因: {_vm_status_cache.error_message}"

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
                    "📋 任务状态",
                    f"任务ID: {data.get('id', task_id)}",
                    f"标题: {data.get('title', '未知')}",
                    f"状态: {status} {status_emoji}",
                ]

                if data.get("exit_code") is not None:
                    result_lines.append(f"退出码: {data['exit_code']}")

                result_lines.append(f"创建时间: {_format_datetime(data.get('created_at'))}")

                if data.get("started_at"):
                    result_lines.append(f"开始时间: {_format_datetime(data['started_at'])}")

                if data.get("finished_at"):
                    result_lines.append(f"完成时间: {_format_datetime(data['finished_at'])}")

                # 处理输出
                output = data.get("output", "")
                if output:
                    truncated_output, was_truncated = _truncate_output(output)
                    result_lines.append("")
                    result_lines.append("📤 输出内容:")
                    result_lines.append(truncated_output)
                    if was_truncated:
                        result_lines.append("")
                        result_lines.append(f"（输出内容过长，仅显示最后 {OUTPUT_MAX_LENGTH} 个字符）")
                else:
                    result_lines.append("")
                    result_lines.append("📤 输出内容: (无)")

                return "\n".join(result_lines)

            elif response.status_code == 404:
                return f"❌ 找不到任务\n任务ID: {task_id}"
            else:
                return f"❌ 查询任务状态失败\n状态码: {response.status_code}\n响应: {response.text}"

    except httpx.TimeoutException:
        return "❌ 请求超时，无法查询任务状态"
    except Exception as e:
        logger.exception(e)
        return f"❌ 查询任务状态时发生错误: {str(e)}"


async def vm_send_input(task_id: str, input_text: str) -> str:
    """
    向正在运行的任务发送输入

    Args:
        task_id: 任务 ID
        input_text: 要发送的输入内容

    Returns:
        发送结果
    """
    if not is_vm_available():
        return f"❌ VM 服务当前不可用\n原因: {_vm_status_cache.error_message}"

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
                return f"""✅ 输入已发送
任务ID: {task_id}
发送内容: {display_input}"""

            elif response.status_code == 404:
                return f"❌ 找不到任务\n任务ID: {task_id}"
            elif response.status_code == 400:
                return f"❌ 任务未在运行中，无法发送输入\n任务ID: {task_id}"
            else:
                return f"❌ 发送输入失败\n状态码: {response.status_code}\n响应: {response.text}"

    except httpx.TimeoutException:
        return "❌ 请求超时，无法发送输入"
    except Exception as e:
        logger.exception(e)
        return f"❌ 发送输入时发生错误: {str(e)}"


async def vm_stop_task(task_id: str) -> str:
    """
    停止正在运行的任务

    Args:
        task_id: 任务 ID

    Returns:
        停止结果
    """
    if not is_vm_available():
        return f"❌ VM 服务当前不可用\n原因: {_vm_status_cache.error_message}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{_get_base_url()}/tasks/{task_id}",
                headers=_get_headers(),
            )

            if response.status_code == 200:
                return f"""🛑 任务已停止
任务ID: {task_id}"""

            elif response.status_code == 404:
                return f"❌ 找不到任务\n任务ID: {task_id}"
            else:
                return f"❌ 停止任务失败\n状态码: {response.status_code}\n响应: {response.text}"

    except httpx.TimeoutException:
        return "❌ 请求超时，无法停止任务"
    except Exception as e:
        logger.exception(e)
        return f"❌ 停止任务时发生错误: {str(e)}"


def get_vm_tools() -> List:
    """
    获取 VM 相关的工具函数列表

    Returns:
        AsyncFunction 对象列表
    """
    from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter

    return [
        AsyncFunction(
            func=vm_create_task,
            description=(
                "在远程 Docker 容器中创建一个命令执行任务。\n"
                "**何时调用**:\n"
                "- 当需要执行系统命令、运行脚本或进行系统操作时\n"
                "- 当需要编译或运行代码时\n"
                "- 当需要查看系统信息、文件内容或进行文件操作时\n"
                "**使用流程**:\n"
                "1. 调用此工具创建任务，获得任务 ID\n"
                "2. 使用 vm_get_task_state 查询任务执行结果\n"
                "3. 如果任务需要交互式输入，使用 vm_send_input 发送输入\n"
                "4. 如果需要终止长时间运行的任务，使用 vm_stop_task\n"
                "**注意事项**:\n"
                "- 命令将在 Linux 环境的 Docker 容器中执行\n"
                "- 任务是异步执行的，创建后需查询状态获取结果\n"
                "- 对于长时间运行的命令，任务状态会显示为 running"
            ),
            parameters={
                "command": FunctionParameter(
                    type="string",
                    description=(
                        "要在 Docker 容器中执行的 Shell 命令。"
                        "支持所有标准的 Linux Shell 命令，如 ls、cat、python、gcc 等。"
                        "可以使用管道、重定向等 Shell 特性。"
                        "例如: 'ls -la /tmp' 或 'python3 script.py' 或 'echo hello > test.txt'"
                    ),
                    required=True,
                ),
                "title": FunctionParameter(
                    type="string",
                    description=(
                        "任务标题，用于描述这个任务的用途。"
                        "应简洁明了地说明任务目的，便于后续追踪和管理。"
                        "例如: '查看系统信息'、'运行测试脚本'、'编译程序'"
                    ),
                    required=True,
                ),
            },
        ),
        AsyncFunction(
            func=vm_get_task_state,
            description=(
                "获取指定任务的执行状态和输出内容。\n"
                "**何时调用**:\n"
                "- 在使用 vm_create_task 创建任务后，查询任务执行结果\n"
                "- 需要检查长时间运行的任务是否完成\n"
                "- 需要获取任务的输出内容\n"
                "**任务状态说明**:\n"
                "- pending: 任务等待执行\n"
                "- running: 任务正在执行\n"
                "- completed: 任务执行完成（成功）\n"
                "- failed: 任务执行失败\n"
                "- stopped: 任务被手动停止"
            ),
            parameters={
                "task_id": FunctionParameter(
                    type="string",
                    description=("由 vm_create_task 返回的任务 ID。" "格式为 UUID，例如: '550e8400-e29b-41d4-a716-446655440000'"),
                    required=True,
                ),
            },
        ),
        AsyncFunction(
            func=vm_send_input,
            description=(
                "向正在运行的任务的标准输入（stdin）发送内容。\n"
                "**何时调用**:\n"
                "- 当任务需要交互式输入时（如程序等待用户输入）\n"
                "- 当需要回答程序的提示问题时（如 yes/no 确认）\n"
                "**注意事项**:\n"
                "- 只能向状态为 running 的任务发送输入\n"
                "- 如果需要发送换行符以模拟按下回车键，请在内容末尾添加 \\n\n"
                "- 发送后可使用 vm_get_task_state 查看任务响应"
            ),
            parameters={
                "task_id": FunctionParameter(
                    type="string",
                    description="正在运行的任务的 ID",
                    required=True,
                ),
                "input_text": FunctionParameter(
                    type="string",
                    description=(
                        "要发送到任务标准输入的内容。"
                        "如需模拟按下回车键，请在末尾添加换行符 \\n。"
                        "例如: 'yes\\n' 表示输入 yes 并按回车"
                    ),
                    required=True,
                ),
            },
        ),
        AsyncFunction(
            func=vm_stop_task,
            description=(
                "停止一个正在运行的任务。\n"
                "**何时调用**:\n"
                "- 当任务运行时间过长需要终止时\n"
                "- 当发现任务执行的命令有误需要中断时\n"
                "- 当不再需要任务继续执行时\n"
                "**注意事项**:\n"
                "- 停止后的任务无法恢复\n"
                "- 任务状态将变为 stopped"
            ),
            parameters={
                "task_id": FunctionParameter(
                    type="string",
                    description="要停止的任务的 ID",
                    required=True,
                ),
            },
        ),
    ]


# 注册定时任务检查 VM 状态
if is_vm_configured():

    @scheduler.scheduled_job("interval", seconds=60, id="check_vm_status")
    async def _scheduled_vm_check() -> None:
        """定时检查 VM 服务状态"""
        await _check_vm_status()

    # 启动时立即检查一次
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

    import asyncio

    asyncio.get_event_loop().call_soon(lambda: asyncio.create_task(_initial_vm_check()))