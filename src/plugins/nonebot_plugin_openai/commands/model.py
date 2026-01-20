"""
/model 命令处理器
仅 superuser 可用
"""

from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_larkutils import get_user_id, is_user_superuser

from ..utils.client import client
from ..utils.model_config import (
    get_default_model,
    get_model_override,
    remove_model_for_identify,
    set_default_model,
    set_model_for_identify,
)


model_cmd = on_alconna(
    Alconna(
        "/model",
        Args["model_name?", str]["identify?", str],
    ),
    block=True,
)


@model_cmd.handle()
async def handle_model(
    model_name: str | None = None,
    identify: str | None = None,
    is_superuser: bool = is_user_superuser(),
    user_id: str = get_user_id(),
) -> None:
    if not is_superuser:
        await model_cmd.finish("权限不足：只有 superuser 可以使用此命令")

    # 无参数：显示可用模型列表和当前配置
    if model_name is None:
        await show_model_info()
        return

    # 只有模型名：更换默认模型
    if identify is None:
        await set_default_model(model_name)
        await model_cmd.finish(f"✅ 已将默认模型设置为: {model_name}")
        return

    # 模型名 + 应用标识：修改特定应用的模型
    if model_name == ":default:":
        # 删除该应用的模型配置
        if await remove_model_for_identify(identify):
            await model_cmd.finish(f"✅ 已删除应用 {identify} 的模型配置，将使用默认模型")
        else:
            await model_cmd.finish(f"⚠️ 应用 {identify} 没有特定的模型配置")
    else:
        await set_model_for_identify(identify, model_name)
        await model_cmd.finish(f"✅ 已将应用 {identify} 的模型设置为: {model_name}")


async def show_model_info() -> None:
    """显示可用模型列表和当前配置"""
    # 获取可用模型列表
    try:
        models_response = await client.models.list()
        available_models = [model.id for model in models_response.data]
        models_list = "\n".join(f"  - {model}" for model in sorted(available_models))
    except Exception as e:
        models_list = f"  ⚠️ 获取模型列表失败: {e}"

    # 获取当前配置
    default_model = await get_default_model()
    model_override = await get_model_override()

    # 构建特殊配置显示
    if model_override:
        override_list = "\n".join(
            f"  - {identify}: {model}" for identify, model in model_override.items()
        )
    else:
        override_list = "  (无特殊配置)"

    message = f"""📋 模型配置信息

🔹 默认模型: {default_model}

🔹 应用特殊配置:
{override_list}

🔹 可用模型列表:
{models_list}

📝 使用方法:
  /model - 显示此信息
  /model <模型名> - 更换默认模型
  /model <模型名> <应用标识> - 设置应用模型
  /model :default: <应用标识> - 删除应用配置"""

    await model_cmd.finish(message)
