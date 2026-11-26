#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

"""塔罗牌抽取工具：整副 78 张牌用 ``secrets`` 随机抽取，保证结果不可预测"""

import secrets
from dataclasses import dataclass

from nonebot_plugin_chat.types import GetTextFunc


@dataclass(frozen=True)
class TarotCard:
    name: str
    english_name: str
    upright: str
    reversed: str


@dataclass(frozen=True)
class SpreadPosition:
    name: str
    hint: str


MAJOR_ARCANA: tuple[TarotCard, ...] = (
    TarotCard(
        "愚者",
        "The Fool",
        "新的开始、冒险与无限可能，保持纯真与信任。",
        "鲁莽、逃避责任、计划不周，先别急着迈步。",
    ),
    TarotCard(
        "魔术师",
        "The Magician",
        "创造力、行动力与资源整合，你已具备实现目标的条件。",
        "欺骗、能力未发挥或计划落空，警惕花言巧语。",
    ),
    TarotCard(
        "女祭司",
        "The High Priestess",
        "直觉、潜意识与内在智慧，答案需要静下来才能听见。",
        "忽视直觉、秘密被揭穿或情感封闭。",
    ),
    TarotCard(
        "皇后",
        "The Empress",
        "丰饶、滋养与创造力，温柔地照顾自己和他人。",
        "过度依赖、创造力受阻或忽视自我照顾。",
    ),
    TarotCard(
        "皇帝",
        "The Emperor",
        "秩序、权威与稳定，用规则和责任感掌控局面。",
        "专制、固执或失去掌控，警惕硬碰硬。",
    ),
    TarotCard(
        "教皇",
        "The Hierophant",
        "传统、信仰与指导，遵循既有规则或寻求导师。",
        "打破常规、教条主义或价值观冲突。",
    ),
    TarotCard("恋人", "The Lovers", "爱、结合与重要选择，跟随内心真实的渴望。", "关系失衡、错误选择或价值观分歧。"),
    TarotCard("战车", "The Chariot", "意志力、胜利与前进，掌控方向就能克服障碍。", "失控、方向不明或被情绪驱使。"),
    TarotCard("力量", "Strength", "勇气、耐心与温柔的力量，以柔克刚。", "自我怀疑、软弱或被情绪吞噬。"),
    TarotCard("隐士", "The Hermit", "内省、独处与寻求真理，暂时退后想清楚。", "孤立、逃避或拒绝他人的帮助。"),
    TarotCard("命运之轮", "Wheel of Fortune", "转机、循环与好运，顺势而为。", "厄运、停滞或抗拒变化。"),
    TarotCard("正义", "Justice", "公平、真相与因果，做出理性的判断。", "不公、偏见或逃避责任。"),
    TarotCard("倒吊人", "The Hanged Man", "暂停、牺牲与换位思考，放下执念换个角度。", "无谓牺牲、拖延或拒绝改变。"),
    TarotCard("死神", "Death", "结束与转化，旧事物退场，为新事物让路。", "抗拒结束、停滞不前或无法放下。"),
    TarotCard("节制", "Temperance", "平衡、调和与耐心，找到中庸之道。", "失衡、极端或缺乏耐心。"),
    TarotCard("恶魔", "The Devil", "欲望、束缚与执念，正视诱惑与依赖。", "挣脱束缚、觉醒或放下执念。"),
    TarotCard("高塔", "The Tower", "突变、崩塌与真相揭露，破而后立。", "避免灾难、延迟改变或内在崩塌。"),
    TarotCard("星星", "The Star", "希望、疗愈与灵感，保持信念。", "失望、信心不足或与内心失去连接。"),
    TarotCard("月亮", "The Moon", "迷茫、幻象与潜意识，答案尚不明朗。", "拨云见日、释放恐惧或真相浮现。"),
    TarotCard("太阳", "The Sun", "成功、喜悦与活力，坦然享受当下。", "短暂低落、过度乐观或快乐受阻。"),
    TarotCard("审判", "Judgement", "觉醒、重生与召唤，回应内心的声音。", "自我怀疑、逃避审视或错失时机。"),
    TarotCard("世界", "The World", "完成、圆满与整合，一个阶段顺利收尾。", "未竟之事、停滞或缺少收尾。"),
)

WANDS: tuple[TarotCard, ...] = (
    TarotCard("权杖王牌", "Ace of Wands", "灵感迸发、新机会与行动的火种。", "动力不足、时机未到或计划受阻。"),
    TarotCard("权杖二", "Two of Wands", "规划未来、做出选择、眺望远方。", "犹豫不决、缺乏规划或安于现状。"),
    TarotCard("权杖三", "Three of Wands", "拓展视野、进展顺利、等待回报。", "延迟、目光短浅或计划受挫。"),
    TarotCard("权杖四", "Four of Wands", "庆祝、稳定与归属感。", "缺乏安全感、庆祝延迟或家庭摩擦。"),
    TarotCard("权杖五", "Five of Wands", "竞争、冲突与磨合。", "回避冲突、内耗或竞争结束。"),
    TarotCard("权杖六", "Six of Wands", "胜利、认可与自信。", "缺乏认可、骄傲自满或成功延迟。"),
    TarotCard("权杖七", "Seven of Wands", "坚持立场、捍卫成果、迎接挑战。", "力不从心、退缩或放弃抵抗。"),
    TarotCard("权杖八", "Eight of Wands", "快速进展、消息传来、顺势行动。", "延迟、混乱或沟通不畅。"),
    TarotCard("权杖九", "Nine of Wands", "坚韧、警觉与最后的坚持。", "疲惫、防备过度或准备放弃。"),
    TarotCard("权杖十", "Ten of Wands", "责任沉重、压力与坚持到底。", "放下负担、学会分担或过度劳累。"),
    TarotCard("权杖侍从", "Page of Wands", "热情、探索与新消息。", "三分钟热度、方向不明或坏消息。"),
    TarotCard("权杖骑士", "Knight of Wands", "行动、冒险与热情推进。", "冲动、鲁莽或半途而废。"),
    TarotCard("权杖王后", "Queen of Wands", "自信、魅力与温暖的能量。", "嫉妒、自我怀疑或精力耗竭。"),
    TarotCard("权杖国王", "King of Wands", "领导力、远见与果断行动。", "专制、急躁或滥用权力。"),
)

CUPS: tuple[TarotCard, ...] = (
    TarotCard("圣杯王牌", "Ace of Cups", "情感萌发、爱与直觉的源泉。", "情感封闭、失望或爱意受阻。"),
    TarotCard("圣杯二", "Two of Cups", "相互吸引、伙伴关系与和谐。", "关系失衡、误解或分手危机。"),
    TarotCard("圣杯三", "Three of Cups", "友谊、庆祝与分享快乐。", "社交疲惫、三角关系或过度放纵。"),
    TarotCard("圣杯四", "Four of Cups", "倦怠、错过机会与情绪内耗。", "重新振作、接受新机会或走出低谷。"),
    TarotCard("圣杯五", "Five of Cups", "失落、遗憾与专注失去的部分。", "释怀、接受现实或重新出发。"),
    TarotCard("圣杯六", "Six of Cups", "怀旧、纯真与旧日情谊。", "沉溺过去、无法向前或童年阴影。"),
    TarotCard("圣杯七", "Seven of Cups", "选择过多、幻想与不切实际。", "看清现实、做出决定或减少选项。"),
    TarotCard("圣杯八", "Eight of Cups", "离开、寻找更深的意义与情感满足。", "害怕改变、原地徘徊或逃避内心。"),
    TarotCard("圣杯九", "Nine of Cups", "满足、愿望成真与享受当下。", "贪心、表面满足或愿望落空。"),
    TarotCard("圣杯十", "Ten of Cups", "圆满、家庭幸福与情感归属。", "关系破裂、家庭失和或理想幻灭。"),
    TarotCard("圣杯侍从", "Page of Cups", "情感细腻、新的感受与创意。", "情绪化、不成熟或逃避现实。"),
    TarotCard("圣杯骑士", "Knight of Cups", "浪漫、追随内心与真诚邀约。", "花言巧语、情绪不稳或承诺落空。"),
    TarotCard("圣杯王后", "Queen of Cups", "共情、温柔与情感智慧。", "情绪依赖、过度敏感或失去边界。"),
    TarotCard("圣杯国王", "King of Cups", "情感成熟、包容与稳定支持。", "情感操控、冷漠或压抑情绪。"),
)

SWORDS: tuple[TarotCard, ...] = (
    TarotCard("宝剑王牌", "Ace of Swords", "清晰的思维、真相与突破。", "混乱、误解或判断失误。"),
    TarotCard("宝剑二", "Two of Swords", "僵局、两难与暂时回避。", "打破僵局、做出决定或信息浮现。"),
    TarotCard("宝剑三", "Three of Swords", "心碎、痛苦与尖锐的真相。", "疗愈、释怀或痛苦减轻。"),
    TarotCard("宝剑四", "Four of Swords", "休息、恢复与暂时退场。", "无法休息、焦虑或被迫面对。"),
    TarotCard("宝剑五", "Five of Swords", "冲突、争执与两败俱伤。", "和解、放下胜负或停止内耗。"),
    TarotCard("宝剑六", "Six of Swords", "过渡、离开困境与走向平静。", "停滞、旧问题复发或难以抽身。"),
    TarotCard("宝剑七", "Seven of Swords", "策略、隐瞒与独自行动。", "真相暴露、坦白或计划败露。"),
    TarotCard("宝剑八", "Eight of Swords", "自我设限、困局与无力感。", "挣脱束缚、找到出路或重获自由。"),
    TarotCard("宝剑九", "Nine of Swords", "焦虑、失眠与过度担忧。", "走出焦虑、寻求帮助或噩梦结束。"),
    TarotCard("宝剑十", "Ten of Swords", "结束、谷底与彻底的终结。", "触底反弹、痛苦减轻或新的开始。"),
    TarotCard("宝剑侍从", "Page of Swords", "好奇、求知与敏锐的观察。", "口舌是非、轻率或消息不实。"),
    TarotCard("宝剑骑士", "Knight of Swords", "果断、快速行动与直言不讳。", "鲁莽、攻击性或言语伤人。"),
    TarotCard("宝剑王后", "Queen of Swords", "理性、独立与清晰的边界。", "冷漠、刻薄或过度防备。"),
    TarotCard("宝剑国王", "King of Swords", "智慧、公正与理性决策。", "专断、冷酷或滥用逻辑。"),
)

PENTACLES: tuple[TarotCard, ...] = (
    TarotCard("星币王牌", "Ace of Pentacles", "物质新机、财富与务实的开始。", "机会流失、财务不稳或计划落空。"),
    TarotCard("星币二", "Two of Pentacles", "平衡、灵活与兼顾多事。", "失衡、分身乏术或财务混乱。"),
    TarotCard("星币三", "Three of Pentacles", "协作、专业与初步成果。", "团队不和、质量不足或缺乏认可。"),
    TarotCard("星币四", "Four of Pentacles", "守成、安全感与掌控资源。", "吝啬、过度执着或财务失控。"),
    TarotCard("星币五", "Five of Pentacles", "匮乏、困顿与相互扶持。", "走出困境、获得援助或财务好转。"),
    TarotCard("星币六", "Six of Pentacles", "慷慨、给予与接受、收支平衡。", "施舍失衡、债务或附带条件的帮助。"),
    TarotCard("星币七", "Seven of Pentacles", "耐心、长期投入与等待收获。", "缺乏耐心、投入无回报或方向错误。"),
    TarotCard("星币八", "Eight of Pentacles", "专注、精进与踏实积累。", "敷衍、重复劳动或缺乏进步。"),
    TarotCard("星币九", "Nine of Pentacles", "独立、富足与享受成果。", "过度依赖、表面光鲜或财务焦虑。"),
    TarotCard("星币十", "Ten of Pentacles", "富足、家族传承与长期稳定。", "财务纠纷、家庭矛盾或根基不稳。"),
    TarotCard("星币侍从", "Page of Pentacles", "学习、务实与新的机会。", "拖延、眼高手低或错失良机。"),
    TarotCard("星币骑士", "Knight of Pentacles", "勤勉、可靠与稳步推进。", "停滞、固执或工作倦怠。"),
    TarotCard("星币王后", "Queen of Pentacles", "务实、滋养与理财智慧。", "过度操劳、物质焦虑或忽视自己。"),
    TarotCard("星币国王", "King of Pentacles", "富足、稳健与商业头脑。", "贪婪、固执或物质至上。"),
)

TAROT_CARDS: tuple[TarotCard, ...] = MAJOR_ARCANA + WANDS + CUPS + SWORDS + PENTACLES

SPREADS: dict[str, tuple[SpreadPosition, ...]] = {
    "single": (SpreadPosition("指引", "这张牌给你的核心提示"),),
    "three": (
        SpreadPosition("过去", "影响当前局面的过去因素"),
        SpreadPosition("现在", "当下的状态与处境"),
        SpreadPosition("未来", "事情的发展趋势"),
    ),
    "celtic_cross": (
        SpreadPosition("现状", "你目前所处的情况"),
        SpreadPosition("挑战", "横在面前的阻碍或对立面"),
        SpreadPosition("远因", "潜意识或更深层的根源"),
        SpreadPosition("近因", "刚刚过去、正在消退的影响"),
        SpreadPosition("潜在目标", "你内心真正想要的结果"),
        SpreadPosition("近期未来", "接下来可能发生的事"),
        SpreadPosition("自我认知", "你如何看待自己"),
        SpreadPosition("外部环境", "周围人或环境的影响"),
        SpreadPosition("希望与恐惧", "你期待或害怕的事"),
        SpreadPosition("最终结果", "综合以上因素的可能走向"),
    ),
}

# 模型有时会把牌型写成中文或简写，这里统一映射到标准 key
_SPREAD_ALIASES: dict[str, str] = {
    "single": "single",
    "one": "single",
    "1": "single",
    "单张": "single",
    "单牌": "single",
    "一张": "single",
    "three": "three",
    "3": "three",
    "三张": "three",
    "三牌": "three",
    "past_present_future": "three",
    "celtic_cross": "celtic_cross",
    "celtic": "celtic_cross",
    "cross": "celtic_cross",
    "10": "celtic_cross",
    "ten": "celtic_cross",
    "凯尔特十字": "celtic_cross",
    "十字": "celtic_cross",
    "十张": "celtic_cross",
}


def normalize_spread(spread: str) -> str:
    """把牌型参数归一化为 ``SPREADS`` 中的 key"""
    key = spread.strip().lower().replace("-", "_").replace(" ", "_")
    return _SPREAD_ALIASES.get(key, key)


def draw_cards(count: int) -> list[tuple[TarotCard, bool]]:
    """用 ``secrets`` 从整副牌中无放回抽取 ``count`` 张，并随机决定正逆位

    Returns:
        ``(牌, 是否逆位)`` 列表，顺序即牌阵位置顺序
    """
    if count < 1:
        raise ValueError("count must be positive")
    if count > len(TAROT_CARDS):
        raise ValueError("count exceeds deck size")

    deck = list(TAROT_CARDS)
    drawn: list[tuple[TarotCard, bool]] = []
    for _ in range(count):
        card = deck.pop(secrets.randbelow(len(deck)))
        drawn.append((card, secrets.randbelow(2) == 0))
    return drawn


async def draw_tarot_cards(spread: str, question: str, get_text: GetTextFunc) -> str:
    """按牌阵抽取塔罗牌并返回各位置的牌与含义

    Args:
        spread: 牌型 key（single / three / celtic_cross，兼容中文与简写）
        question: 提问者的问题，会原样出现在返回结果中
        get_text: 本地化文本获取函数

    Returns:
        格式化后的占卜结果；牌型无效时返回带可选牌型的提示
    """
    spread_key = normalize_spread(spread)
    positions = SPREADS.get(spread_key)
    if positions is None:
        available = "、".join([f"{key}（{await get_text(f'tarot.spread.{key}')}）" for key in SPREADS])
        return await get_text("tarot.invalid_spread", spread, available, question)

    cards = draw_cards(len(positions))
    spread_name = await get_text(f"tarot.spread.{spread_key}")
    items = [
        await get_text(
            "tarot.item",
            position.name,
            position.hint,
            card.name,
            card.english_name,
            await get_text("tarot.reversed" if is_reversed else "tarot.upright"),
            card.reversed if is_reversed else card.upright,
        )
        for position, (card, is_reversed) in zip(positions, cards)
    ]
    return await get_text("tarot.header", question, spread_name) + "\n\n" + "\n\n".join(items)
