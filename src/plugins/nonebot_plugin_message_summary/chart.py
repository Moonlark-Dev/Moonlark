from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager
from io import BytesIO
from typing import List
from .models import CatGirlScore
from .lang import lang

# 添加中文字体支持
font_manager.fontManager.addfont(Path(".").joinpath("src/static/SarasaGothicSC-Regular.ttf"))
plt.rcParams["font.sans-serif"] = ["Sarasa Gothic SC"]
plt.rcParams["axes.unicode_minus"] = False


async def render_horizontal_bar_chart(scores: List[CatGirlScore], user_id: str) -> bytes:
    """
    使用matplotlib生成横向柱状图
    
    Args:
        scores: CatGirlScore对象列表，包含rank, username, score字段
        
    Returns:
        bytes: 图片的字节数据
    """
    if not scores:
        # 如果没有数据，返回空图片
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, await lang.text("neko.no_data", user_id), ha='center', va='center', transform=ax.transAxes, fontsize=16)
        ax.axis('off')
        
        buf = BytesIO()
        plt.savefig(buf, format="png", bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()
    
    # 提取数据
    usernames = [score["username"] for score in scores]
    user_scores = [score["score"] for score in scores]
    ranks = [score["rank"] for score in scores]
    
    # 创建横向柱状图
    fig, ax = plt.subplots(figsize=(12, max(6, len(scores) * 0.5)))  # 根据数据量调整高度
    
    # 生成颜色映射，前3名使用特殊颜色
    colors = []
    for rank in ranks:
        if rank == 1:
            colors.append('#FFD700')  # 金色
        elif rank == 2:
            colors.append('#C0C0C0')  # 银色
        elif rank == 3:
            colors.append('#CD7F32')  # 铜色
        else:
            colors.append('#4E73DF')  # 默认蓝色
    
    # 创建横向柱状图
    bars = ax.barh(range(len(usernames)), user_scores, color=colors)
    
    # 设置y轴标签
    ax.set_yticks(range(len(usernames)))
    ax.set_yticklabels(usernames)
    
    # 设置x轴标签
    ax.set_xlabel(await lang.text("neko.x_label", user_id))
    
    # 设置标题
    ax.set_title(await lang.text("neko.title", user_id), fontsize=16, fontweight='bold', pad=20)
    
    # 在每个柱子上显示数值和排名
    for i, (bar, score, rank) in enumerate(zip(bars, user_scores, ranks)):
        # 显示分数值
        ax.text(bar.get_width() + max(user_scores) * 0.01, bar.get_y() + bar.get_height()/2, 
                f'{score}', va='center', ha='left', fontweight='bold')
        # 显示排名
        ax.text(max(user_scores) * 0.01, bar.get_y() + bar.get_height()/2, 
                f'#{rank}', va='center', ha='left', fontweight='bold', 
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
    
    # 反转y轴，使第一名在最上方
    ax.invert_yaxis()
    
    # 添加网格线
    ax.grid(axis='x', alpha=0.3)
    
    # 调整布局
    plt.tight_layout()
    
    # 保存到 BytesIO
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight', dpi=300)
    buf.seek(0)
    plt.close(fig)  # 关闭图以释放资源
    
    return buf.getvalue()