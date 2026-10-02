"""AI 工具定义（src/prompt/__tools__/*.yaml）的参数名必须与包装函数签名一致

create_function_list() 用 YAML 里声明的参数名以关键字形式调用包装函数
（nonebot_plugin_openai/utils/chat.py: `func(**params)`）。两边名字不一致时，模型只要
调用该工具就会抛 TypeError，而异常会被 tool_executor 吞成一行「执行工具 xxx 时发生错误」，
从聊天记录里很难看出是定义写错了。所以这里对两条真实的注册路径做全量比对。
"""

import inspect
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "src" / "prompt" / "__tools__"


def _assert_tools_are_consistent(tools: list[Any]) -> None:
    """工具定义里声明的参数名必须与 func 的签名逐一对应（既不能多也不能少）"""
    assert tools, "工具列表为空，注册路径可能已经变了"

    for tool in tools:
        func = tool["func"]
        name = func.__name__
        declared = set(tool["parameters"])
        actual = set(inspect.signature(func).parameters)

        assert (TOOLS_DIR / f"{name}.yaml").is_file(), f"{name} 没有对应的工具定义文件"
        assert declared == actual, (
            f"{name}: 工具定义声明的参数 {sorted(declared)} 与函数签名 {sorted(actual)} 不一致，"
            "模型按定义调用时会抛 TypeError"
        )


async def test_chat_common_tool_parameters_are_callable() -> None:
    """chat 插件的通用工具（含 search_abbreviation）：定义里的参数名能被函数按关键字接收"""
    from nonebot_plugin_chat.utils.tool_manager import ToolManager

    _assert_tools_are_consistent(await ToolManager().select_tools("agent"))


async def test_wdym_tool_parameters_are_callable() -> None:
    """wdym 插件复用同一批工具定义，参数名同样要能落到包装函数上"""
    from nonebot_plugin_wdym.utils import WdymTools

    _assert_tools_are_consistent(await WdymTools("0").get_tools())
