import matplotlib.pyplot as plt
from io import BytesIO
from ...lang import lang

plt.rcParams["font.sans-serif"] = ["??????"]
plt.rcParams["axes.unicode_minus"] = False


async def render_pie(data, sender_id):
    labels = list(data.keys())
    sizes = list(data.values())
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct="%d", startangle=90)
    ax.set_title(await lang.text("stat.title", sender_id))
    ax.axis("equal")
    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
