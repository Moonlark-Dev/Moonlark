"""
/model 命令处理器
仅 superuser 可用
"""

from nonebot_plugin_alconna import Alconna, Args, MultiVar, on_alconna
from nonebot_plugin_larkutils import get_user_id, is_user_superuser

from ..lang import lang
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
        "model",
        Args["model_name?", str]["identify_parts?", MultiVar(str, "*")],
    )
)


@model_cmd.handle()
async def handle_model(
    model_name: str | None = None,
    identify_parts: tuple[str, ...] | None = None,
    is_superuser: bool = is_user_superuser(),
    user_id: str = get_user_id(),
) -> None:
    # 将多个部分合并为一个应用标识（支持带空格的标识）
    identify: str | None = " ".join(identify_parts) if identify_parts else None
    if not is_superuser:
        await lang.finish("model.no_permission", user_id)

    # 无参数：显示可用模型列表和当前配置
    if model_name is None:
        await show_model_info(user_id)
        return

    # 只有模型名：更换默认模型
    if identify is None:
        await set_default_model(model_name)
        await lang.finish("model.set_default", user_id, model_name)
        return

    # 模型名 + 应用标识：修改特定应用的模型
    if model_name == ":default:":
        # 删除该应用的模型配置
        if await remove_model_for_identify(identify):
            await lang.finish("model.remove_identify", user_id, identify)
        else:
            await lang.finish("model.no_identify_config", user_id, identify)
    else:
        await set_model_for_identify(identify, model_name)
        await lang.finish("model.set_identify", user_id, identify, model_name)


async def show_model_info(user_id: str) -> None:
    """显示可用模型列表和当前配置"""
    # 获取可用模型列表
    try:
        models_response = await client.models.list()
        available_models = [model.id for model in models_response.data]
        models_list = "\n".join(f"{model}" for model in sorted(available_models))
    except Exception as e:
        models_list = await lang.text("model.models_list_failed", user_id, str(e))

    # 获取当前配置
    default_model = await get_default_model()
    model_override = await get_model_override()

    # 构建特殊配置显示
    if model_override:
        override_list = "\n".join(f" - {identify}: {model}" for identify, model in model_override.items())
    else:
        override_list = await lang.text("model.no_override", user_id)

    await lang.finish(
        "model.info",
        user_id,
        default_model=default_model,
        override_list=override_list,
        models_list=models_list,
    )
