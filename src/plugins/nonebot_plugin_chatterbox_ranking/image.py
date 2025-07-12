from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager
from io import BytesIO
from .lang import lang

from .models import GroupChatterboxWithNickname

font_manager.fontManager.addfont(Path(".").joinpath("src/static/SarasaGothicSC-Regular.ttf"))
plt.rcParams["font.sans-serif"] = ["Sarasa Gothic SC"]
plt.rcParams["axes.unicode_minus"] = False


async def render_bar(data: list[GroupChatterboxWithNickname], sender_id: str, group_id: str) -> bytes:
    nicknames = [item.nickname for item in data]
    counts = [item.message_count for item in data]
    # 创建条形图
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(nicknames, counts)
    ax.set_xlabel(await lang.text("bar.x_label", sender_id))
    ax.set_ylabel(await lang.text("bar.y_label", sender_id))
    fig.suptitle(await lang.text("bar.main_title", sender_id), fontsize=16, fontweight='bold')  # 主标题
    ax.set_title(group_id, fontsize=12, pad=20)  # 副标题
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # 保存到 BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)  # 关闭图以释放资源

    return buf.getvalue()