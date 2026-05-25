from nonebot_plugin_render import render_template, generate_render_keys
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_alconna import UniMessage
from .lang import lang
from .chart import render_horizontal_bar_chart
from .models import CatGirlScore, DebateAnalysis
from .ai_utils import DecisionResult


async def render_summary_result(summary_string: str, style: str) -> UniMessage:
    if style == "topic":
        return UniMessage().image(raw=await md_to_pic(summary_string))
    else:
        return UniMessage().image(raw=await md_to_pic(summary_string))


async def render_neko_result(catgirl_scores: list[CatGirlScore], user_id: str) -> UniMessage:
    image_bytes = await render_horizontal_bar_chart(catgirl_scores, user_id)
    return UniMessage().image(raw=image_bytes)


async def render_debate_result(debate_data: DebateAnalysis, user_id: str) -> UniMessage:
    keys = await generate_render_keys(
        lang, user_id, ["standpoint", "arguments", "implicit", "fallacies", "analysis_title", "render_title"], "debate."
    )
    image = await render_template(
        "debate.html.jinja",
        keys["render_title"],
        user_id,
        {"data": debate_data},
        keys=keys,
        viewport={"width": 1600, "height": 900},
    )
    return UniMessage().image(raw=image)


async def render_history_check_result(result: dict, user_id: str) -> UniMessage:
    """Render the history check result card"""
    keys = await generate_render_keys(lang, user_id, ["title", "sender", "time", "content"], "check_history.")

    # Sanitization is handled by Jinja2 autoescape=True in render_template

    image = await render_template(
        "history_check.html.jinja",
        keys["title"],
        user_id,
        {"result": result},
        keys=keys,
    )
    return UniMessage().image(raw=image)


async def render_decision_notice(
    decision_data: DecisionResult,
    target_nickname: str,
    group_name: str,
    punishment: str,
    user_id: str,
) -> UniMessage:
    """渲染处分通知图片

    Args:
        decision_data: AI 生成的处分内容
        target_nickname: 目标群员昵称
        group_name: 群名称
        punishment: 处分内容（如"女装"）
        user_id: 用户ID
    """
    from datetime import datetime

    # 生成文档编号（基于当前年份和随机数）
    current_year = datetime.now().year
    doc_number = f"{datetime.now().strftime('%m%d')}{datetime.now().second:02d}"

    # 渲染模板数据
    template_data = {
        "group_name": group_name,
        "year": current_year,
        "doc_number": doc_number,
        "target_nickname": target_nickname,
        "violation_time": datetime.now().strftime("%Y年%m月%d日"),
        "violation_background": decision_data.background,
        "violation_details": decision_data.violations,
        "punishment": punishment,
        "rectification_requirements": decision_data.rectification,
        "date": datetime.now().strftime("%Y年%m月%d日"),
    }

    image = await render_template(
        "decision.html.jinja",
        "处分决定",
        user_id,
        template_data,
    )
    return UniMessage().image(raw=image)
