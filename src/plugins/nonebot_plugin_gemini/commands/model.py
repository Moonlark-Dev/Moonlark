"""``/gem-model`` 命令处理器

仅 superuser 可用，行为与 OpenAI 插件的 ``/model`` 一致：不带参数时展示模型配置与
可用模型列表；带模型名时更换默认模型；带模型名与应用标识时设置该应用的专用模型。
"""

from nonebot_plugin_alconna import Alconna, Args, MultiVar, on_alconna
from nonebot_plugin_larkutils import get_user_id, is_user_superuser

from ..lang import lang
from ..utils.client import get_client
from ..utils.model_config import (
    get_default_model,
    get_model_override,
    remove_model_for_identify,
    set_default_model,
    set_model_for_identify,
)

gem_model_cmd = on_alconna(
    Alconna(
        "gem-model",
        Args["model_name?", str]["identify_parts?", MultiVar(str, "*")],
    )
)


@gem_model_cmd.handle()
async def handle_gem_model(
    model_name: str | None = None,
    identify_parts: tuple[str, ...] | None = None,
    is_superuser: bool = is_user_superuser(),
    user_id: str = get_user_id(),
) -> None:
    # 将多个部分合并为一个应用标识（支持带空格的标识）
    identify: str | None = " ".join(identify_parts) if identify_parts else None
    if not is_superuser:
        await lang.finish("gem_model.no_permission", user_id)

    # 无参数：显示可用模型列表和当前配置
    if model_name is None:
        await show_model_info(user_id)
        return

    # 只有模型名：更换默认模型
    if identify is None:
        await set_default_model(model_name)
        await lang.finish("gem_model.set_default", user_id, model_name)
        return

    # 模型名 + 应用标识：修改特定应用的模型
    if model_name == ":default:":
        # 删除该应用的模型配置
        if await remove_model_for_identify(identify):
            await lang.finish("gem_model.remove_identify", user_id, identify)
        else:
            await lang.finish("gem_model.no_identify_config", user_id, identify)
    else:
        await set_model_for_identify(identify, model_name)
        await lang.finish("gem_model.set_identify", user_id, identify, model_name)


async def show_model_info(user_id: str) -> None:
    """显示可用模型列表和当前配置"""
    try:
        pager = await get_client().aio.models.list()
        model_names = sorted({model.name for model in [item async for item in pager] if model.name is not None})
        models_list = "\n".join(model_names)
    except Exception as e:
        models_list = await lang.text("gem_model.models_list_failed", user_id, str(e))

    default_model = await get_default_model()
    model_override = await get_model_override()

    if model_override:
        override_list = "\n".join(f" - {identify}: {model}" for identify, model in model_override.items())
    else:
        override_list = await lang.text("gem_model.no_override", user_id)

    await lang.finish(
        "gem_model.info",
        user_id,
        default_model=default_model,
        override_list=override_list,
        models_list=models_list,
    )
