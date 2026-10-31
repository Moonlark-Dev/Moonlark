"""Token 计费口径与被 @ 轮次免计费额度的回归测试。

计费只按「有效字」：标点、语气词不计费（单条最多豁免 12 个），每 8 个有效字 1 Token，
每条消息至少 1 Token。被 @ / 重要事件触发的那一轮，首条消息即使 Token 为负也放行，
100 字以内不计费。
"""

# 图 2 参考里的三句（用于钉住「自然说法不比压缩说法贵」的计费口径）
_REFERENCE_SENTENCES = [
    "唔……1块钱想借1亿？那还不如去买张彩票呢，至少彩票不会刚买完就碎掉呀喵",
    "因为杠杆越高死得越快嘛！平时开个10倍，价格反着走10%本金就清零了。要是真开1亿倍，哪怕价格只往反方向动那么一丁点，你那1块钱啪的一下就没了喵，平台才不陪你玩这种一秒爆仓的游戏呢",
    "平时本金亏完确实会强平啦，但万一行情跳得太快、平台来不及平单，就会穿仓倒欠钱的喵！借你1个亿，万一穿仓了你拿小鱼干赔给人家嘛～",
]


def _cost_module():
    from nonebot_plugin_chat.utils import token_cost

    return token_cost


def test_empty_message_costs_nothing() -> None:
    assert _cost_module().calculate_token_cost("") == 0


def test_particle_only_message_costs_one_token() -> None:
    """纯语气词消息不能免费——否则「喵～」可以无限刷"""
    assert _cost_module().calculate_token_cost("喵～") == 1
    assert _cost_module().calculate_token_cost("！！！！！") == 1


def test_exempt_chars_are_capped_per_message() -> None:
    """豁免有上限：30 个喵只免 12 个，剩下 18 个有效字按 8 字/Token 计费"""
    module = _cost_module()

    assert module.exempt_char_count("喵" * 30) == 12
    assert module.effective_length("喵" * 30) == 18
    assert module.calculate_token_cost("喵" * 30) == 3


def test_particles_and_punctuation_do_not_add_cost() -> None:
    """同样的内容，语气词和标点不额外收费：旧口径多扣 1 Token，去掉标点成本不变"""
    import math

    module = _cost_module()
    sentence = "平时本金亏完确实会强平啦，但万一行情跳得太快、平台来不及平单，就会穿仓倒欠钱的喵！"
    no_punctuation = "平时本金亏完确实会强平啦但万一行情跳得太快平台来不及平单就会穿仓倒欠钱的喵"

    assert module.calculate_token_cost(sentence) == 5
    assert math.ceil(len(sentence) / 7) == 6
    # 标点全拆掉，成本不变：它们本来就不该算钱
    assert module.calculate_token_cost(no_punctuation) == module.calculate_token_cost(sentence)


def test_reference_sentences_stay_affordable() -> None:
    """图 2 的写法：一条完整的解释句落在 4~11 Token，不再被 7 字口径罚成天价"""
    module = _cost_module()

    costs = [module.calculate_token_cost(sentence) for sentence in _REFERENCE_SENTENCES]
    assert costs == [4, 11, 7]


def test_natural_reply_is_cheaper_than_old_formula() -> None:
    """32 字的自然回复：旧口径 5 Token，新口径 4 Token"""
    import math

    sentence = "今天中午咱去食堂吃了炸鸡，还喝了冰可乐，感觉整个人都活过来了喵～"
    old_cost = math.ceil(len(sentence) / 7)

    assert old_cost == 5
    assert _cost_module().calculate_token_cost(sentence) == 4


class _TokenCostProbe:
    """只实现额度判定所需接口的处理器替身"""

    IMPORTANT_FREE_REPLY_CHARS = 100

    def __init__(self, token: float, quota: bool = False) -> None:
        from nonebot_plugin_chat.utils.token_bucket import TokenBucket

        self.token_bucket = TokenBucket(6, -2)
        self.token_bucket.token = token
        self.important_turn_quota = quota


def _resolve(probe: object, text: str) -> int | None:
    from nonebot_plugin_chat.core.processor import MessageProcessor

    return MessageProcessor._resolve_message_token_cost(probe, text)  # type: ignore[arg-type]  # ruff: ignore[private-member-access]


def test_negative_bucket_without_quota_blocks() -> None:
    probe = _TokenCostProbe(-1)

    assert _resolve(probe, "记得带伞喵～") is None


def test_important_turn_first_message_is_free_and_consumes_quota() -> None:
    probe = _TokenCostProbe(-1, quota=True)

    assert _resolve(probe, "平时本金亏完确实会强平啦，但万一行情跳得太快就会穿仓倒欠钱的喵！") == 0
    # 额度一轮只用一次
    assert probe.important_turn_quota is False
    assert _resolve(probe, "咱接着说喵") is None


def test_important_turn_over_length_is_charged_normally() -> None:
    probe = _TokenCostProbe(-1, quota=True)
    long_text = "喵" * 150

    cost = _resolve(probe, long_text)

    assert cost is not None
    assert cost > 0
    assert probe.important_turn_quota is False


def test_positive_bucket_still_charges_normally() -> None:
    probe = _TokenCostProbe(3)

    assert _resolve(probe, "记得带伞喵～") == 1
    assert probe.important_turn_quota is False
