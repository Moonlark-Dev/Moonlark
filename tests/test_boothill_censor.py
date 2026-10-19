def test_censor_standard_replaces_ma_words_only() -> None:
    """标准模式仅替换拼音以 ma 开头的词"""
    from nonebot_plugin_boothill.censor import censor

    assert censor("妈", "standard") == "他宝贝的"
    # 非编码前的词应保持不变
    assert censor("草", "standard") == "草"
    assert censor("笨蛋", "standard") == "笨蛋"


def test_censor_standard_skips_words_with_ma_only_after_first_syllable() -> None:
    """标准模式不命中拼音以 ma 开头的词出现在词首以外的情况"""
    from nonebot_plugin_boothill.censor import censor

    # 词首拼音是 cao 而非 ma，标准模式不替换（fury 模式会替换）
    assert censor("草泥马", "standard") == "草泥马"


def test_censor_fury_keeps_current_rules() -> None:
    """狂怒模式沿用现行替换规则（c/q/m/s/b 开头的拼音）"""
    from nonebot_plugin_boothill.censor import censor

    assert censor("草泥马", "fury") == "喵"
    assert censor("妈", "fury") == "他宝贝的"
    assert censor("草", "fury") == "喵"
    assert censor("笨蛋", "fury") == "可爱"


def test_censor_default_mode_is_standard() -> None:
    from nonebot_plugin_boothill.censor import censor

    assert censor("妈") == "他宝贝的"
    assert censor("草") == "草"
