from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager
from io import BytesIO
from ...lang import lang

font_manager.fontManager.addfont(Path(".").joinpath("src/static/SarasaGothicSC-Regular.ttf"))
plt.rcParams["font.sans-serif"] = ["Sarasa Gothic SC"]
plt.rcParams["axes.unicode_minus"] = False


async def render_pie(data, sender_id):
    absolute_value = lambda pct: int(pct / 100.0 * sum(data.values()))
    labels = list(data.keys())
    sizes = list(data.values())
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct=absolute_value, startangle=90)
    ax.set_title(await lang.text("stat.title", sender_id))
    ax.axis("equal")
    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
