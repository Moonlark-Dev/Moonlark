"""“缩略”（Missing Abbreviations）的题目校验、去重、缓存、纯本地判题、免费提示与多端交互测试。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def make_question(
    full_word: str = "人民代表大会",
    breakdown: str = "[人]民代表[大]会",
    question: str = "民代表会",
    answers: Any = None,
    hint: Any = None,
    difficulty: int = 2,
    tags: Any = None,
) -> Any:
    """构造一道结构合法的《缩略》题目。"""
    from nonebot_plugin_missing_abbreviations.types import GeneratedQuestion

    return GeneratedQuestion(
        full_word=full_word,
        breakdown=breakdown,
        question=question,
        answers=["人大"] if answers is None else answers,
        hint=["○民代表○会", "国家权力机关"] if hint is None else hint,
        difficulty=difficulty,
        tags={} if tags is None else tags,
    )


# ---------- 1. 答案归一化与精确匹配 ----------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("ＳｒＹ", "sry"),
        ("Ｚｎ", "zn"),
        ("Zn", "zn"),
        ("Ph.D.", "ph.d."),
        ("i. e.", "i.e."),
        (" e . g . ", "e.g."),
        ("ｅ．ｇ．", "e.g."),
        ("ｕ１ｓ１", "u1s1"),
        ("　人　大　", "人大"),
        ("人\t大", "人大"),
    ],
)
def test_normalize_answer_handles_nfkc_case_and_whitespace(left: str, right: str) -> None:
    from nonebot_plugin_missing_abbreviations.store import is_exact_match, normalize_answer

    assert normalize_answer(left) == normalize_answer(right)
    assert is_exact_match(left, right)


@pytest.mark.parametrize(
    ("with_punct", "without_punct"),
    [
        ("etc.", "etc"),
        ("e.g.", "eg"),
        ("i.e.", "ie"),
        ("R&D", "RD"),
        ("Ph.D.", "PhD"),
        ("a-b", "ab"),
    ],
)
def test_normalize_answer_strictly_preserves_punctuation(with_punct: str, without_punct: str) -> None:
    from nonebot_plugin_missing_abbreviations.store import is_exact_match, normalize_answer

    assert normalize_answer(with_punct) != normalize_answer(without_punct)
    assert not is_exact_match(with_punct, without_punct)


# ---------- 2. Pydantic 校验器（GeneratedQuestion） ----------


def test_generated_question_answers_validator_accepts_str_and_list() -> None:
    from nonebot_plugin_missing_abbreviations.types import GeneratedQuestion

    single = make_question(answers="  人大  ")
    assert single.answers == ["人大"]
    assert single.primary_answer == "人大"

    multiple = make_question(
        full_word="exempli gratia",
        breakdown="[e]xempli [g]ratia",
        question="xempliratia",
        answers=[" e.g. ", "eg", "   "],
        hint=["○xempli ○ratia"],
    )
    assert multiple.answers == ["e.g.", "eg"]
    assert multiple.primary_answer == "e.g."

    empty = make_question(answers=["   "])
    assert empty.answers == []
    assert empty.primary_answer == ""

    with pytest.raises(TypeError):
        GeneratedQuestion(
            full_word="人民代表大会",
            breakdown="[人]民代表[大]会",
            question="民代表会",
            answers=123,  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        GeneratedQuestion(
            full_word="人民代表大会",
            breakdown="[人]民代表[大]会",
            question="民代表会",
            answers=[123],  # type: ignore[list-item]
        )


def test_generated_question_hint_validator_splits_semicolons_and_normalizes_circles() -> None:
    from nonebot_plugin_missing_abbreviations.types import GeneratedQuestion

    from_str = make_question(hint=" 〇民代表◯会 ; 国家机构 ； 政治常识 ;  ")
    assert from_str.hint == ["○民代表○会", "国家机构", "政治常识"]

    from_list = make_question(hint=["〇民代表◯会", "  ", "国家权力机关"])
    assert from_list.hint == ["○民代表○会", "国家权力机关"]

    from_none = GeneratedQuestion(
        full_word="人民代表大会",
        breakdown="[人]民代表[大]会",
        question="民代表会",
        answers=["人大"],
        hint=None,  # type: ignore[arg-type]
    )
    assert from_none.hint == []

    with pytest.raises(TypeError):
        make_question(hint=42)

    with pytest.raises(TypeError):
        make_question(hint=[42])


def test_generated_question_tags_validator_maps_known_and_drops_disallowed() -> None:
    from nonebot_plugin_missing_abbreviations.types import KNOWN_TAG_DESCRIPTIONS, GeneratedQuestion

    from_list = make_question(tags=["精选", "变格", "谜协", "例题", "未知标签"])
    assert from_list.tags == {
        "精选": KNOWN_TAG_DESCRIPTIONS["精选"],
        "变格": KNOWN_TAG_DESCRIPTIONS["变格"],
    }
    assert "谜协" not in from_list.tags
    assert "例题" not in from_list.tags

    from_dict = make_question(
        tags={
            "精选": "自定义精选说明",
            "多解": "   ",
            "词源": None,
            "谜协": "不允许的标签",
            "例题": "不允许的标签",
        },
    )
    assert from_dict.tags == {
        "精选": "自定义精选说明",
        "多解": KNOWN_TAG_DESCRIPTIONS["多解"],
        "词源": KNOWN_TAG_DESCRIPTIONS["词源"],
    }

    from_none = GeneratedQuestion(
        full_word="人民代表大会",
        breakdown="[人]民代表[大]会",
        question="民代表会",
        answers=["人大"],
        tags=None,  # type: ignore[arg-type]
    )
    assert from_none.tags == {}

    with pytest.raises(TypeError):
        make_question(tags="精选")

    with pytest.raises(TypeError):
        make_question(tags=[123])

    with pytest.raises(TypeError):
        make_question(tags={"精选": 123})


# ---------- 3. 拆解解析器（parse_breakdown）与恒等式校验（is_valid_question） ----------


def test_valid_chinese_standard_puzzle() -> None:
    from nonebot_plugin_missing_abbreviations.store import is_valid_question, parse_breakdown

    puzzle = make_question(
        full_word="人民代表大会",
        breakdown="[人]民代表[大]会",
        question="民代表会",
        answers=["人大"],
        hint=["○民代表○会"],
    )
    parsed = parse_breakdown(puzzle.breakdown)
    assert parsed == ("人民代表大会", "人大", "民代表会", "○民代表○会")
    assert is_valid_question(puzzle)


def test_valid_english_dotted_abbreviation_puzzle() -> None:
    from nonebot_plugin_missing_abbreviations.store import is_valid_question, parse_breakdown

    puzzle = make_question(
        full_word="exempli gratia",
        breakdown="[e]xempli [g]ratia",
        question="xempliratia",
        answers=["e.g.", "eg"],
        hint=["○xempli ○ratia", "拉丁语常见缩写"],
        difficulty=3,
    )
    parsed = parse_breakdown(puzzle.breakdown)
    assert parsed == ("exempli gratia", "eg", "xempli ratia", "○xempli ○ratia")
    assert is_valid_question(puzzle)


def test_valid_biange_romanization_and_pinyin_puzzles() -> None:
    from nonebot_plugin_missing_abbreviations.store import is_valid_question

    u1s1_puzzle = make_question(
        full_word="有一说一",
        breakdown="yo[u]yi[1][s]huoyi[1]",
        question="yoyihuoyi",
        answers=["u1s1"],
        hint=["yo○yi○○huoyi○", "网络流行语谐音缩写"],
        difficulty=4,
        tags=["变格"],
    )
    assert is_valid_question(u1s1_puzzle)

    yyds_puzzle = make_question(
        full_word="永远的神",
        breakdown="[y]ong[y]uan[d]e[s]hen",
        question="onguanehen",
        answers=["yyds"],
        hint=["○ong○uan○e○hen", "网络流行语拼音首字母"],
        difficulty=4,
        tags={"变格": "涉及拼音、罗马音或数字谐音层面的娱乐向拆解"},
    )
    assert is_valid_question(yyds_puzzle)

    # 未标注「变格」标签时，汉字 full_word 与拼音 breakdown 不一致必须被拒绝
    missing_biange_tag = make_question(
        full_word="永远的神",
        breakdown="[y]ong[y]uan[d]e[s]hen",
        question="onguanehen",
        answers=["yyds"],
        hint=["○ong○uan○e○hen"],
        difficulty=4,
        tags={},
    )
    assert not is_valid_question(missing_biange_tag)


@pytest.mark.parametrize(
    "bad_breakdown",
    [
        "[]人民代表大会",
        "[   ]人民代表大会",
        "[[人]]民代表[大]会",
        "[人[民]]代表大会",
        "[人民代表大会",
        "人民]代表[大会",
        "人民代表大会]",
        "人民代表大会",
    ],
)
def test_parse_breakdown_rejects_malformed_brackets(bad_breakdown: str) -> None:
    from nonebot_plugin_missing_abbreviations.store import parse_breakdown

    assert parse_breakdown(bad_breakdown) is None


def test_is_valid_question_rejects_hallucinated_abbreviations() -> None:
    from nonebot_plugin_missing_abbreviations.store import is_valid_question

    # 「鲁」不在「山东省」中
    shandong_mismatch_answer = make_question(
        full_word="山东省",
        breakdown="[山]东省",
        question="东省",
        answers=["鲁"],
        hint=["○东省"],
    )
    shandong_fake_breakdown = make_question(
        full_word="山东省",
        breakdown="[鲁]山东省",
        question="山东省",
        answers=["鲁"],
        hint=["○山东省"],
    )
    assert not is_valid_question(shandong_mismatch_answer)
    assert not is_valid_question(shandong_fake_breakdown)

    # 「Pb」不在「lead」中
    lead_mismatch_answer = make_question(
        full_word="lead",
        breakdown="[l]ea[d]",
        question="ea",
        answers=["Pb"],
        hint=["○ea○"],
    )
    lead_fake_breakdown = make_question(
        full_word="lead",
        breakdown="[Pb]lead",
        question="lead",
        answers=["Pb"],
        hint=["○○lead"],
    )
    assert not is_valid_question(lead_mismatch_answer)
    assert not is_valid_question(lead_fake_breakdown)


def test_is_valid_question_rejects_question_mask_difficulty_and_answer_violations() -> None:
    from nonebot_plugin_missing_abbreviations.store import is_valid_question

    # question 漏字或多字（unbracketed != question）
    assert not is_valid_question(make_question(question="民代表"))
    assert not is_valid_question(make_question(question="人民代表会"))

    # hint[0] 的 ○ 骨架掩码不匹配、提示为空或超过 2 条
    assert not is_valid_question(make_question(hint=["○民代表会"]))
    assert not is_valid_question(make_question(hint=["[人]民代表[大]会"]))
    assert not is_valid_question(make_question(hint=[]))
    assert not is_valid_question(make_question(hint=["○民代表○会", "机关", "多余提示"]))

    # 空题面、空原词、空答案
    assert not is_valid_question(
        make_question(full_word="人大", breakdown="[人大]", question="", answers=["人大"], hint=["○○"]),
    )
    assert not is_valid_question(make_question(full_word="   "))
    assert not is_valid_question(make_question(answers=[]))

    # 难度越界
    assert not is_valid_question(make_question(difficulty=0))
    assert not is_valid_question(make_question(difficulty=6))

    # 答案等于原词或等于题面
    assert not is_valid_question(make_question(answers=["人大", "人民代表大会"]))
    assert not is_valid_question(make_question(answers=["人大", "民代表会"]))

    # 字段包含换行符
    assert not is_valid_question(make_question(full_word="人民\n代表大会"))
    assert not is_valid_question(make_question(breakdown="[人]民\n代表[大]会"))
    assert not is_valid_question(make_question(question="民代\r表会"))
    assert not is_valid_question(make_question(answers=["人\n大"]))
    assert not is_valid_question(make_question(hint=["○民代表○会", "国家\n机关"]))
    assert not is_valid_question(make_question(tags={"精选": "第一行\n第二行"}))


def test_format_question_markdown_and_answer_summary() -> None:
    from nonebot_plugin_missing_abbreviations.store import (
        format_answer_summary,
        format_difficulty,
        format_question,
        format_question_markdown,
    )

    assert format_difficulty(3) == "★★★☆☆ (3/5)"
    assert format_difficulty(9) == "★★★★★ (5/5)"

    standard = make_question(tags=["精选"])
    plain = format_question(standard, revealed_hints=0)
    assert "【缩略】" in plain
    assert "题面：民代表会" in plain
    assert "可用提示：2 条（免费）" in plain

    md_unrevealed = format_question_markdown(standard, revealed_hints=0)
    assert "| 题面 | 难度 |" in md_unrevealed
    assert "**民代表会**" in md_unrevealed
    assert "**💡 可用提示**：2 条（免费）" in md_unrevealed
    assert "<" not in md_unrevealed
    assert ">" not in md_unrevealed

    md_revealed = format_question_markdown(standard, revealed_hints=1)
    assert "**💡 提示 1**：○民代表○会" in md_revealed
    assert "<" not in md_revealed
    assert ">" not in md_revealed

    assert format_answer_summary(standard) == ("人大", "[人]民代表[大]会")

    biange = make_question(
        full_word="永远的神",
        breakdown="[y]ong[y]uan[d]e[s]hen",
        question="onguanehen",
        answers=["yyds", "YYDS "],
        hint=["○ong○uan○e○hen"],
        tags=["变格"],
    )
    answers_disp, origin_disp = format_answer_summary(biange)
    assert answers_disp == "yyds / YYDS"
    assert origin_disp == "永远的神 → [y]ong[y]uan[d]e[s]hen"


# ---------- 4. 内置例题黑名单、去重与本地缓存（filter_questions & QuestionStore） ----------


@pytest.mark.parametrize(
    ("full_word", "breakdown", "question", "answers", "hint", "tags"),
    [
        ("奥林匹克运动会", "[奥]林匹克[运]动[会]", "林匹克动", ["奥运会"], ["○林匹克○动○"], {}),
        (
            "普通高等学校招生全国统一考试",
            "普通[高]等学校招生全国统一[考]试",
            "普通等学校招生全国统一试",
            ["高考"],
            ["普通○等学校招生全国统一○试"],
            {},
        ),
        ("德克萨斯州", "[德]克萨斯[州]", "克萨斯", ["德州"], ["○克萨斯○"], {}),
        ("得克萨斯州", "得[克]萨[斯]州", "得萨州", ["克斯"], ["得○萨○州"], {}),
        ("然而并没有什么卵用", "[然]而[并]没有什么[卵]用", "而没有什么用", ["然并卵"], ["○而○没有什么○用"], {}),
        ("zinc", "[z]i[n]c", "ic", ["Zn"], ["○i○c"], {}),
        ("silicon", "[s][i]licon", "licon", ["Si"], ["○○licon"], {}),
        ("sorry", "[s]o[r]r[y]", "or", ["sry"], ["○o○r○"], {}),
        ("etcetera", "[e][t][c]etera", "etera", ["etc.", "etc"], ["○○○etera"], {}),
        ("id est", "[i]d [e]st", "dst", ["i.e.", "ie"], ["○d ○st"], {}),
        ("芝麻酱", "芝[麻][酱]", "芝", ["麻酱"], ["芝○○"], {}),
        ("芝麻油", "芝[麻][油]", "芝", ["麻油"], ["芝○○"], {}),
        ("ここ好き", "[k]o[k]o[s]u[k]i", "ooui", ["kksk"], ["○o○o○u○i"], ["变格"]),
        ("有一说一", "yo[u]yi[1][s]huoyi[1]", "yoyihuoyi", ["u1s1"], ["yo○yi○○huoyi○"], ["变格"]),
    ],
)
def test_filter_questions_rejects_all_builtin_banned_examples(
    full_word: str,
    breakdown: str,
    question: str,
    answers: list[str],
    hint: list[str],
    tags: Any,
) -> None:
    from nonebot_plugin_missing_abbreviations.store import filter_questions, is_valid_question

    candidate = make_question(
        full_word=full_word,
        breakdown=breakdown,
        question=question,
        answers=answers,
        hint=hint,
        tags=tags,
    )
    assert is_valid_question(candidate)
    assert filter_questions([candidate], [], [], []) == []


def test_filter_questions_dedupes_batch_internal_and_history() -> None:
    from nonebot_plugin_missing_abbreviations.store import filter_questions

    q1 = make_question()
    same_full_word = make_question(
        full_word=" 人民代表大会 ",
        breakdown="[人]民[代]表大会",
        question="民表大会",
        answers=["人代"],
        hint=["○民○表大会"],
    )
    same_answer = make_question(
        full_word="中国人民大学",
        breakdown="中国[人]民[大]学",
        question="中国民学",
        answers=[" 人 大 "],
        hint=["中国○民○学"],
    )
    same_question_surface = make_question(
        full_word="国民代表大会",
        breakdown="[国]民代表[大]会",
        question="民代表会",
        answers=["国大"],
        hint=["○民代表○会"],
    )
    q2 = make_question(
        full_word="科学技术",
        breakdown="[科]学[技]术",
        question="学术",
        answers=["科技"],
        hint=["○学○术"],
    )

    accepted = filter_questions([q1, same_full_word, same_answer, same_question_surface, q2], [], [], [])
    assert accepted == [q1, q2]

    # 命中历史原词、历史答案或历史题面时均应过滤
    assert filter_questions([q1], ["人民代表大会"], [], []) == []
    assert filter_questions([q1], [], ["人大"], []) == []
    assert filter_questions([q1], [], [], ["民代表会"]) == []


@pytest.mark.asyncio
async def test_question_store_persistence_pop_ensure_ready_and_prefetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from nonebot_plugin_missing_abbreviations import store as store_module

    q1 = make_question()
    q2 = make_question(
        full_word="科学技术",
        breakdown="[科]学[技]术",
        question="学术",
        answers=["科技"],
        hint=["○学○术"],
    )
    q3 = make_question(
        full_word="人工智能",
        breakdown="[人][工][智][能]",
        question="",  # 非法题面应被过滤
        answers=["人工智能"],
        hint=["○○○○"],
    )

    path = tmp_path / "questions.json"
    store = store_module.QuestionStore(path, generate_count=5, low_water=2, history_size=10)
    assert await store.extend([q1, make_question(answers=[" 人大 "]), q3]) == 1
    assert await store.count() == 1

    # 缓存非空时 ensure_ready 不会触发生成
    gen_calls: list[tuple[list[str], list[str], int]] = []
    prefetch_done = asyncio.Event()

    async def fake_generate(
        excluded_full_words: list[str],
        excluded_answers: list[str],
        count: int,
    ) -> list[Any]:
        gen_calls.append((excluded_full_words, excluded_answers, count))
        prefetch_done.set()
        return [q2]

    monkeypatch.setattr(store_module, "generate_questions", fake_generate)
    await store.ensure_ready()
    assert gen_calls == []

    # pop 取出唯一题目并落盘
    popped = await store.pop()
    assert popped is not None
    assert popped.primary_answer == "人大"
    assert await store.count() == 0
    assert await store.pop() is None

    # 重新加载文件：历史记录持久化生效，同一道题不会再次入库
    reloaded = store_module.QuestionStore(path, generate_count=5, low_water=2, history_size=10)
    assert await reloaded.extend([q1]) == 0
    assert "人民代表大会" in reloaded.recent_full_words
    assert "人大" in reloaded.recent_answers
    assert "民代表会" in reloaded.recent_questions

    # 空缓存调用 ensure_ready 时同步生成新题并传入历史去重列表
    await reloaded.ensure_ready()
    assert len(gen_calls) == 1
    assert "人民代表大会" in gen_calls[0][0]
    assert "人大" in gen_calls[0][1]
    assert gen_calls[0][2] == 5
    assert await reloaded.count() == 1

    # 题量低于 low_water=2 时 schedule_prefetch 后台补题
    q_extra = make_question(
        full_word="社会主义核心价值观",
        breakdown="社会主义[核]心[价]值[观]",
        question="社会主义心值",
        answers=["核价观"],
        hint=["社会主义○心○值○"],
    )

    async def fake_generate_prefetch(
        _excluded_full_words: list[str],
        _excluded_answers: list[str],
        _count: int,
    ) -> list[Any]:
        res = [q_extra]
        prefetch_done.set()
        return res

    prefetch_done.clear()
    monkeypatch.setattr(store_module, "generate_questions", fake_generate_prefetch)
    reloaded.schedule_prefetch()
    await asyncio.wait_for(prefetch_done.wait(), timeout=2.0)
    # 让 _prefetch 协程完成 extend 落盘
    for _ in range(10):
        if await reloaded.count() >= 2:
            break
        await asyncio.sleep(0.01)
    assert await reloaded.count() == 2


def test_get_question_store_uses_localstore_and_build_extra() -> None:
    from nonebot_plugin_missing_abbreviations.store import build_generation_extra, get_question_store

    store = get_question_store()
    assert store.path.name == "questions.json"
    assert store.path.parent.name == "nonebot_plugin_missing_abbreviations"

    extra = build_generation_extra(["人民代表大会"], ["人大"], 20)
    assert "20" in extra
    assert "JSON 数组" in extra
    assert "人民代表大会" in extra
    assert "人大" in extra


# ---------- 5. 题目生成参数（identify、超时与数据结构） ----------


def test_config_does_not_hardcode_model_and_uses_600s_timeout() -> None:
    from nonebot_plugin_missing_abbreviations.config import Config

    default_cfg = Config()
    assert not hasattr(default_cfg, "missing_abbreviations_model")
    assert default_cfg.missing_abbreviations_generate_timeout == 600


@pytest.mark.asyncio
async def test_generate_questions_passes_identify_timeout_and_schema_to_fetch_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nonebot_plugin_missing_abbreviations import store as store_module
    from nonebot_plugin_missing_abbreviations.types import GeneratedQuestion

    sample = make_question()
    captured: dict[str, Any] = {}

    async def fake_get_message(role: str, name: str) -> Any:
        return store_module.generate_message(f"{role}:{name}", "system")

    async def fake_fetch_json(messages: list[Any], response_format: Any, **kwargs: Any) -> list[GeneratedQuestion]:
        captured["messages"] = messages
        captured["response_format"] = response_format
        captured["kwargs"] = kwargs
        return [sample]

    monkeypatch.setattr(store_module, "get_message", fake_get_message)
    monkeypatch.setattr(store_module, "fetch_json", fake_fetch_json)

    result = await store_module.generate_questions(["人民代表大会"], ["人大"], 20)
    assert result == [sample]
    assert len(captured["messages"]) == 2
    assert "missing_abbreviations/system.md.jinja" in captured["messages"][0]["content"]
    assert "人民代表大会" in captured["messages"][1]["content"]
    assert "人大" in captured["messages"][1]["content"]
    assert captured["response_format"] == list[GeneratedQuestion]
    assert "model" not in captured["kwargs"]
    assert captured["kwargs"]["identify"] == "Missing Abbreviations (Generate)"
    assert captured["kwargs"]["timeout"] == 600


# ---------- 6. 纯本地判题（judge_guess） ----------


def test_judge_guess_correct_full_word_and_wrong() -> None:
    from nonebot_plugin_missing_abbreviations.judge import judge_guess

    dotted_only = make_question(
        full_word="etcetera",
        breakdown="[e][t][c]etera",
        question="etera",
        answers=["etc."],
        hint=["○○○etera"],
    )
    assert judge_guess("etc.", dotted_only) == "correct"
    assert judge_guess("  ＥＴＣ． ", dotted_only) == "correct"
    # 未收录去点变体时，严格区分标点
    assert judge_guess("etc", dotted_only) == "wrong"
    assert judge_guess("etcetera", dotted_only) == "full_word"
    assert judge_guess("  EtCeTeRa  ", dotted_only) == "full_word"
    assert judge_guess("etera", dotted_only) == "wrong"
    assert judge_guess("   ", dotted_only) == "wrong"
    assert judge_guess("", dotted_only) == "wrong"

    dual_dotted = make_question(
        full_word="exempli gratia",
        breakdown="[e]xempli [g]ratia",
        question="xempliratia",
        answers=["e.g.", "eg"],
        hint=["○xempli ○ratia"],
    )
    assert judge_guess("e.g.", dual_dotted) == "correct"
    assert judge_guess("e. g.", dual_dotted) == "correct"
    assert judge_guess("EG", dual_dotted) == "correct"
    assert judge_guess("exempli gratia", dual_dotted) == "full_word"

    # 变格题同时识别汉字原词与 breakdown 还原出的拼音/罗马音原词为 full_word
    biange = make_question(
        full_word="永远的神",
        breakdown="[y]ong[y]uan[d]e[s]hen",
        question="onguandehen",
        answers=["yyds"],
        hint=["○ong○uan○e○hen"],
        tags=["变格"],
    )
    assert judge_guess("YYDS", biange) == "correct"
    assert judge_guess("永远的神", biange) == "full_word"
    assert judge_guess("yong yuan de shen", biange) == "full_word"
    assert judge_guess("onguandehen", biange) == "wrong"


# ---------- 7. 游戏主循环、免费提示、原词防误判与多适配器交互（MissingAbbreviationsGame & matcher） ----------


def test_game_ownership_non_qq_vs_qq() -> None:
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_missing_abbreviations.game import MissingAbbreviationsGame

    non_qq_game = MissingAbbreviationsGame("session_non_qq", "owner", object(), object())  # type: ignore[arg-type]
    assert non_qq_game.can_answer("owner")
    assert not non_qq_game.can_answer("other")

    qq_bot = create_autospec(QQBot, instance=True)
    qq_game = MissingAbbreviationsGame("session_qq", "owner", qq_bot, object())  # type: ignore[arg-type]
    assert qq_game.can_answer("owner")
    assert qq_game.can_answer("other")


@pytest.mark.asyncio
async def test_game_full_word_trap_free_hints_wrong_and_full_reward(monkeypatch: pytest.MonkeyPatch) -> None:
    """误填原词不扣次数；免费提示渐进解锁 1->2->全部解锁，不扣次数且猜中仍发满额 3 VimCoin。"""
    from nonebot_plugin_missing_abbreviations import game as game_module

    game = game_module.MissingAbbreviationsGame("session_flow", "owner", object(), object())  # type: ignore[arg-type]
    game.question = make_question(
        full_word="人民代表大会",
        breakdown="[人]民代表[大]会",
        question="民代表会",
        answers=["人大"],
        hint=["○民代表○会", "国家权力机关"],
    )

    sent_texts: list[str] = []
    sent_hints: list[str] = []
    sent_results: list[str] = []
    awarded_amounts: list[float] = []

    async def fake_send_text(text: str) -> None:
        sent_texts.append(text)

    async def fake_send_hint(text: str) -> None:
        sent_hints.append(text)

    async def fake_send_result(text: str) -> None:
        sent_results.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    class FakeUser:
        async def add_vimcoin(self, amount: float) -> None:
            awarded_amounts.append(amount)

    async def fake_get_user(_user_id: str) -> FakeUser:
        return FakeUser()

    monkeypatch.setattr(game, "send_text", fake_send_text)
    monkeypatch.setattr(game, "send_hint_message", fake_send_hint)
    monkeypatch.setattr(game, "send_result", fake_send_result)
    monkeypatch.setattr(game_module.lang, "text", fake_text)
    monkeypatch.setattr(game_module, "get_user", fake_get_user)

    initial_attempts = game.attempts_left
    assert initial_attempts == 10

    # 1) 误填原词全称：提醒且不扣作答次数
    await game.handle_guess(game_module.PlayerAction("owner", "人民代表大会", object()))  # type: ignore[arg-type]
    assert game.attempts_left == 10
    assert not game.finished
    assert sent_hints[-1] == "game.full_word_remind:('人民代表大会', 10)"

    # 2) 免费解锁提示 1（○ 骨架掩码）：不扣作答次数
    await game.unlock_hint()
    assert game.hints_revealed == 1
    assert game.attempts_left == 10
    assert "game.hint_unlocked:" in sent_hints[-1]
    assert "game.hint_mask:('○民代表○会',)" in sent_hints[-1]

    # 3) 免费解锁提示 2（领域提示）：不扣作答次数
    await game.unlock_hint()
    assert game.hints_revealed == 2
    assert game.attempts_left == 10
    assert "game.hint_unlocked:" in sent_hints[-1]
    assert "game.hint_mask:('○民代表○会',)" in sent_hints[-1]
    assert "game.hint_extra:(2, '国家权力机关')" in sent_hints[-1]

    # 4) 所有提示已解锁后再次请求提示：展示 all_hints_revealed 且不扣次数
    await game.unlock_hint()
    assert game.hints_revealed == 2
    assert game.attempts_left == 10
    assert sent_hints[-1].startswith("game.all_hints_revealed:")

    # 5) 普通答错：扣除 1 次作答机会
    await game.handle_guess(game_module.PlayerAction("owner", "政协", object()))  # type: ignore[arg-type]
    assert game.attempts_left == 9
    assert not game.finished
    assert sent_texts[-1] == "game.wrong:('政协', 9)"

    # 6) 答对缩略词：即使解锁了全部提示，仍发放完整 3 VimCoin，并同时展示答案与 [ ] 拆解
    await game.handle_guess(game_module.PlayerAction("owner", "人大", object()))  # type: ignore[arg-type]
    assert game.finished
    assert awarded_amounts == [3.0]
    assert sent_results == ["game.correct:('人大', '[人]民代表[大]会', '3')"]


@pytest.mark.asyncio
async def test_game_reveal_now_cancels_task_and_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from nonebot_plugin_missing_abbreviations import game as game_module

    session_id = "session_reveal_now"
    game = game_module.MissingAbbreviationsGame(session_id, "owner", object(), object())  # type: ignore[arg-type]
    game.question = make_question()
    game_module.games[session_id] = game
    sent: list[str] = []
    never_event = asyncio.Event()

    async def fake_send_result(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    monkeypatch.setattr(game, "send_result", fake_send_result)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    task = asyncio.create_task(never_event.wait())
    game.task = task
    try:
        await game.reveal_now()
        await game.reveal_now()

        assert game.finished
        assert session_id not in game_module.games
        assert sent == ["game.reveal_manual:('人大', '[人]民代表[大]会')"]
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        game_module.games.pop(session_id, None)


@pytest.mark.asyncio
async def test_game_reveal_before_question_and_idle_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_missing_abbreviations import game as game_module

    # 题目尚未生成完成时按查看答案
    early = game_module.MissingAbbreviationsGame("session_early", "owner", object(), object())  # type: ignore[arg-type]
    game_module.games["session_early"] = early
    sent_early: list[str] = []

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    monkeypatch.setattr(game_module.lang, "text", fake_text)
    monkeypatch.setattr(early, "send_result", lambda text: _append_async(sent_early, text))
    await early.reveal_now()
    assert early.finished
    assert "session_early" not in game_module.games
    assert sent_early == ["game.reveal_before_question:()"]

    # 三分钟无消息超时自动触发 reveal("timeout")
    class ReadyStore:
        async def count(self) -> int:
            return 5

        async def ensure_ready(self) -> None:
            return None

        async def pop(self) -> Any:
            return make_question()

        def schedule_prefetch(self) -> None:
            return None

    timeout_game = game_module.MissingAbbreviationsGame("session_timeout", "owner", object(), object())  # type: ignore[arg-type]
    sent_timeout: list[str] = []

    async def fake_wait_timeout() -> None:
        return None

    async def noop_send_question() -> None:
        return None

    monkeypatch.setattr(game_module, "get_question_store", lambda: ReadyStore())
    monkeypatch.setattr(timeout_game, "send_question", noop_send_question)
    monkeypatch.setattr(timeout_game, "wait_action", fake_wait_timeout)
    monkeypatch.setattr(timeout_game, "send_result", lambda text: _append_async(sent_timeout, text))

    assert timeout_game.last_activity > 0
    timeout_game.last_activity = 0.0
    assert await game_module.MissingAbbreviationsGame.wait_action(timeout_game) is None

    await timeout_game.run()
    assert timeout_game.finished
    assert sent_timeout == ["game.reveal_timeout:('人大', '[人]民代表[大]会')"]


async def _append_async(bucket: list[str], value: str) -> None:
    bucket.append(value)


@pytest.mark.asyncio
async def test_qq_question_result_and_rules_ui_with_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 QQ 官方 Markdown 表格、row=2 按钮矩阵（解锁完提示后隐藏提示按钮）、结算再来一局按钮与发送失败纯文本回退。"""
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Keyboard, Text
    from nonebot_plugin_larkutils import escape_markdown
    from nonebot_plugin_missing_abbreviations import game as game_module
    from nonebot_plugin_missing_abbreviations.store import format_question_markdown

    labels = {
        "button.start": "开始一局",
        "button.guess": "作答",
        "button.hint": "提示",
        "button.next_hint": "继续提示",
        "button.reveal": "查看答案",
        "button.rules": "规则说明",
        "button.again": "再来一局",
        "game.rules": "纯文本规则",
        "game.rules_markdown": "### 「缩略」规则说明",
        "game.again_hint": "发送 /missing-abbreviations（或 /缩略）可以再来一局。",
    }

    async def fake_text(key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return labels[key]

    monkeypatch.setattr(game_module.lang, "text", fake_text)
    qq_bot = create_autospec(QQBot, instance=True)

    game = game_module.MissingAbbreviationsGame("session_ui", "owner", qq_bot, object())  # type: ignore[arg-type]
    game.question = make_question()

    # 1) 初始题目消息：Markdown 表格 + 作答 / 提示 / 查看答案 / 规则说明（row=2）
    q_msg = await game.build_question_message()
    assert q_msg is not None
    q_text = next(seg for seg in q_msg if isinstance(seg, Text))
    assert q_text.text == format_question_markdown(game.question, revealed_hints=0)
    assert any("markdown" in styles for styles in q_text.styles.values())

    q_kb = next(seg for seg in q_msg if isinstance(seg, Keyboard))
    assert q_kb.row == 2
    assert [(btn.flag, str(btn.label), btn.text) for btn in q_kb.children] == [
        ("input", "作答", "/missing-abbreviations "),
        ("enter", "提示", "/missing-abbreviations 提示"),
        ("enter", "查看答案", "/missing-abbreviations 查看答案"),
        ("enter", "规则说明", "/missing-abbreviations 规则说明"),
    ]

    # 2) 全部提示解锁后，题目消息与规则消息都隐藏「提示」按钮
    game.hints_revealed = len(game.question.hint)
    q_msg_all_hints = await game.build_question_message()
    assert q_msg_all_hints is not None
    q_kb_after = next(seg for seg in q_msg_all_hints if isinstance(seg, Keyboard))
    assert q_kb_after.row == 2
    assert [(btn.flag, str(btn.label), btn.text) for btn in q_kb_after.children] == [
        ("input", "作答", "/missing-abbreviations "),
        ("enter", "查看答案", "/missing-abbreviations 查看答案"),
        ("enter", "规则说明", "/missing-abbreviations 规则说明"),
    ]

    # 3) 规则消息按局外 / 局内（有未解锁提示 vs 已全部解锁）切换按钮，非 QQ 返回纯文本无键盘
    idle_rules = await game_module.build_rules_message(qq_bot, "user", None)
    idle_kb = next(seg for seg in idle_rules if isinstance(seg, Keyboard))
    assert [(btn.flag, str(btn.label), btn.text) for btn in idle_kb.children] == [
        ("enter", "开始一局", "/missing-abbreviations"),
    ]

    game.hints_revealed = 0
    active_rules = await game_module.build_rules_message(qq_bot, "user", game)
    active_kb = next(seg for seg in active_rules if isinstance(seg, Keyboard))
    assert active_kb.row == 2
    assert [(btn.flag, str(btn.label), btn.text) for btn in active_kb.children] == [
        ("input", "作答", "/missing-abbreviations "),
        ("enter", "提示", "/missing-abbreviations 提示"),
        ("enter", "查看答案", "/missing-abbreviations 查看答案"),
    ]

    game.hints_revealed = len(game.question.hint)
    active_no_hint_rules = await game_module.build_rules_message(qq_bot, "user", game)
    active_no_hint_kb = next(seg for seg in active_no_hint_rules if isinstance(seg, Keyboard))
    assert [(btn.flag, str(btn.label), btn.text) for btn in active_no_hint_kb.children] == [
        ("input", "作答", "/missing-abbreviations "),
        ("enter", "查看答案", "/missing-abbreviations 查看答案"),
    ]

    non_qq_rules = await game_module.build_rules_message(object(), "user", game)  # type: ignore[arg-type]
    assert non_qq_rules.extract_plain_text() == "纯文本规则"
    assert not any(isinstance(seg, Keyboard) for seg in non_qq_rules)

    # 4) 结算消息包含「再来一局」按钮，且发送失败时回退纯文本
    raw_result = "🎉 猜对了！答案是「人大」（原词：[人]民代表[大]会），获得 3 VimCoin。"
    res_msg = await game.build_result_message(raw_result)
    res_text = next(seg for seg in res_msg if isinstance(seg, Text))
    assert res_text.text == escape_markdown(raw_result)
    res_kb = next(seg for seg in res_msg if isinstance(seg, Keyboard))
    assert [(btn.flag, str(btn.label), btn.text) for btn in res_kb.children] == [
        ("enter", "再来一局", "/missing-abbreviations"),
    ]

    class BrokenMessage:
        async def send(self, **_kwargs: Any) -> None:
            raise RuntimeError("qq passive reply expired")

    fallback_sent: list[str] = []

    async def broken_build(_text: str) -> Any:
        return BrokenMessage()

    monkeypatch.setattr(game, "build_result_message", broken_build)
    monkeypatch.setattr(game, "send_text", lambda text: _append_async(fallback_sent, text))
    await game.send_result(raw_result)
    assert fallback_sent == [f"{raw_result}\n发送 /missing-abbreviations（或 /缩略）可以再来一局。"]


@pytest.mark.asyncio
async def test_matcher_plain_keywords_noop_when_idle_and_multi_token_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Match
    from nonebot_plugin_missing_abbreviations import game as game_module
    from nonebot_plugin_missing_abbreviations import matcher as matcher_module
    from nonebot_plugin_missing_abbreviations.judge import judge_guess
    from nonebot_plugin_missing_abbreviations.matcher import _is_plain_keyword

    class FakeEvent:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_plaintext(self) -> str:
            return self._text

    # 1) _is_plain_keyword 覆盖全部无前缀中文关键词
    for kw in ("提示", "查看提示", "查看答案", "结束游戏", "结束本局", "规则说明", "  提示  "):
        assert _is_plain_keyword(FakeEvent(kw))  # type: ignore[arg-type]
    assert not _is_plain_keyword(FakeEvent("人大"))  # type: ignore[arg-type]
    assert not _is_plain_keyword(FakeEvent("/missing-abbreviations 提示"))  # type: ignore[arg-type]

    # 2) 当前会话没有进行中的缩略游戏时，handle_plain_command 必须是静默空操作（不抛 FinishedException）
    group_id = "qq_group_idle_test"
    game_module.games.pop(group_id, None)
    for kw in ("提示", "查看答案", "规则说明"):
        await matcher_module.handle_plain_command(
            object(),  # type: ignore[arg-type]
            FakeEvent(kw),  # type: ignore[arg-type]
            group_id=group_id,
            user_id="user_a",
        )

    # 3) 有活跃游戏时：无前缀「提示」触发 unlock_hint；带空格的多词答案 ("e.", "g.") 拼接为 "e. g." 并成功判对
    active_group = "qq_group_active_test"
    active_game = game_module.MissingAbbreviationsGame(
        active_group,
        "owner_u",
        object(),  # type: ignore[arg-type]
        FakeEvent(""),  # type: ignore[arg-type]
    )
    active_game.question = make_question(
        full_word="exempli gratia",
        breakdown="[e]xempli [g]ratia",
        question="xempliratia",
        answers=["e.g.", "eg"],
        hint=["○xempli ○ratia"],
    )
    unlocked_calls = 0

    async def record_unlock() -> None:
        nonlocal unlocked_calls
        unlocked_calls += 1

    monkeypatch.setattr(active_game, "unlock_hint", record_unlock)
    game_module.games[active_group] = active_game
    try:
        # 非房主在非 QQ 适配器下发无前缀「提示」被忽略
        await matcher_module.handle_plain_command(
            object(),  # type: ignore[arg-type]
            FakeEvent("提示"),  # type: ignore[arg-type]
            group_id=active_group,
            user_id="stranger",
        )
        assert unlocked_calls == 0

        # 房主发送无前缀「提示」立即解锁并阻断后续传播
        stopped = False

        def record_stop() -> None:
            nonlocal stopped
            stopped = True

        monkeypatch.setattr(matcher_module.plain_command, "stop_propagation", record_stop)
        with pytest.raises(FinishedException):
            await matcher_module.handle_plain_command(
                object(),  # type: ignore[arg-type]
                FakeEvent("提示"),  # type: ignore[arg-type]
                group_id=active_group,
                user_id="owner_u",
            )
        assert unlocked_calls == 1
        assert stopped is True

        # 多分段/含空格答案经 AllParam UniMessage 提取为 "e. g." 入队并被判为 correct
        from nonebot_plugin_alconna import UniMessage

        with pytest.raises(FinishedException):
            await matcher_module.handle_missing_abbreviations(
                object(),  # type: ignore[arg-type]
                FakeEvent("/ma e. g."),  # type: ignore[arg-type]
                guess=Match(UniMessage("e. g."), available=True),
                group_id=active_group,
                user_id="owner_u",
            )
        queued = active_game.queue.get_nowait()
        assert queued.text == "e. g."
        assert judge_guess(queued.text, active_game.question) == "correct"
    finally:
        game_module.games.pop(active_group, None)


@pytest.mark.asyncio
async def test_alconna_special_inputs_race_guard_and_validation_tightening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回归校验：Alconna 特殊符号解析（-h/?/--/成对单引号）、局间并发不误删新局、标点题面与提示泄底拦截、自动补无点答案及 history_size=0。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_missing_abbreviations import game as game_module
    from nonebot_plugin_missing_abbreviations import store as store_module
    from nonebot_plugin_missing_abbreviations.matcher import _alc, _extract_guess_text
    from nonebot_plugin_missing_abbreviations.store import is_valid_question
    from nonebot_plugin_missing_abbreviations.types import GeneratedQuestion

    # 1) Alconna 禁用内置 help/completion 后，-h、?、--、成对单引号与多词缩写均可原样解析
    from nonebot_plugin_alconna import Match
    from nonebot_plugin_larkutils.command import get_command_prefix

    prefix = get_command_prefix()
    for special in ("-h", "?", "-cp", "--", "rock 'n' roll", "e. g.", "R&D", "C++"):
        parsed = _alc.parse(UniMessage(f"{prefix}missing-abbreviations {special}"))
        assert parsed.matched, f"Alconna 未能匹配特殊输入: {special}"
        guess_match = parsed.query[object]("guess")
        assert _extract_guess_text(Match(guess_match, available=True)) == special

    # 2) 旧局结束清理不会误删同会话刚开的新局
    race_session = "qq_group_race_guard"
    old_game = game_module.MissingAbbreviationsGame(race_session, "u1", object(), object())  # type: ignore[arg-type]
    new_game = game_module.MissingAbbreviationsGame(race_session, "u1", object(), object())  # type: ignore[arg-type]
    game_module.games[race_session] = new_game
    try:
        old_game.stop()
        assert game_module.games.get(race_session) is new_game
    finally:
        game_module.games.pop(race_session, None)

    # 3) 校验器拦截纯标点题面、变格下 question==full_word 以及提示 2 直接泄露答案/原词
    assert not is_valid_question(
        make_question(
            full_word="U.S.A.",
            breakdown="[U].[S].[A].",
            question="...",
            answers=["USA"],
            hint=["○.○.○."],
        ),
    )
    assert not is_valid_question(
        make_question(
            full_word="山东省",
            breakdown="[鲁]山东省",
            question="山东省",
            answers=["鲁"],
            hint=["○山东省"],
            tags=["变格"],
        ),
    )
    assert not is_valid_question(
        make_question(
            full_word="人民代表大会",
            breakdown="[人]民代表[大]会",
            question="民代表会",
            answers=["人大"],
            hint=["○民代表○会", "人大"],
        ),
    )

    # 4) generate_questions 对模型漏写无点形式的带点缩写自动补齐无点别名
    dotted = GeneratedQuestion(
        full_word="exempli gratia",
        breakdown="[e]xempli [g]ratia",
        question="xempliratia",
        answers=["e.g."],
        hint=["○xempli ○ratia"],
    )

    async def fake_get_msg(role: str, name: str) -> Any:
        return store_module.generate_message(f"{role}:{name}", "system")

    async def fake_fetch(_msgs: list[Any], _fmt: Any, **_kwargs: Any) -> list[GeneratedQuestion]:
        return [dotted]

    monkeypatch.setattr(store_module, "get_message", fake_get_msg)
    monkeypatch.setattr(store_module, "fetch_json", fake_fetch)
    generated = await store_module.generate_questions([], [], 5)
    assert generated[0].answers == ["e.g.", "eg"]

    # 5) QuestionStore(history_size=0) 不会保留无限历史（避免 Python list[-0:] 陷阱）
    zero_history_store = store_module.QuestionStore(tmp_path / "zero_hist.json", history_size=0)
    assert await zero_history_store.extend([make_question()]) == 1
    assert zero_history_store.recent_full_words == []
    assert zero_history_store.recent_answers == []
    assert zero_history_store.recent_questions == []


# ---------- 8. 真实 LangHelper 本地化与系统提示词合规性核验 ----------


def _read_repo_file(*parts: str) -> str:
    from pathlib import Path as RuntimePath

    repo_root = RuntimePath(__file__).resolve().parent.parent
    return repo_root.joinpath(*parts).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_real_lang_helper_and_prompt_compliance() -> None:
    """验证 missing_abbreviations.yaml 全量键解析、灵感链接、无裸尖括号，且与提示词均不含违规词。"""
    from nonebot_plugin_larklang.__main__ import load_languages
    from nonebot_plugin_missing_abbreviations.lang import lang
    from nonebot_plugin_openai.utils.message import get_message

    await load_languages()
    user_id = "mlsid::--lang=zh_hans"

    key_calls: list[tuple[str, tuple[Any, ...]]] = [
        ("help.description", ()),
        ("help.details", ()),
        ("help.usage1", ()),
        ("help.usage2", ()),
        ("help.usage3", ()),
        ("help.usage4", ()),
        ("help.usage5", ()),
        ("button.start", ()),
        ("button.guess", ()),
        ("button.hint", ()),
        ("button.next_hint", ()),
        ("button.reveal", ()),
        ("button.rules", ()),
        ("button.again", ()),
        ("game.preparing", ()),
        ("game.preparing_short", ()),
        ("game.generate_failed", ()),
        ("game.error", ()),
        ("game.rules", (10, "3")),
        ("game.rules_markdown", (10, "3")),
        ("game.not_playing_start", ()),
        ("game.already_playing", ()),
        ("game.only_owner", ()),
        ("game.hint_mask", ("○民代表○会",)),
        ("game.hint_extra", (2, "国家权力机关")),
        ("game.hint_unlocked", ("💡 提示 1（骨架掩码）：○民代表○会",)),
        ("game.all_hints_revealed", ("💡 提示 1（骨架掩码）：○民代表○会",)),
        ("game.no_hints_configured", ()),
        ("game.full_word_remind", ("人民代表大会", 10)),
        ("game.correct", ("人大", "[人]民代表[大]会", "3")),
        ("game.correct_no_reward", ("人大", "[人]民代表[大]会")),
        ("game.wrong", ("政协", 9)),
        ("game.reveal_timeout", ("人大", "[人]民代表[大]会")),
        ("game.reveal_manual", ("人大", "[人]民代表[大]会")),
        ("game.reveal_attempts", ("人大", "[人]民代表[大]会")),
        ("game.reveal_before_question", ()),
        ("game.again_hint", ()),
        ("game.hint", ()),
    ]

    resolved_map: dict[str, str] = {}
    for key, args in key_calls:
        text = await lang.text(key, user_id, *args)
        assert text, f"{key} 解析结果为空"
        assert not text.startswith("[缺失:"), f"{key} 缺失本地化条目: {text}"
        resolved_map[key] = text

    inspiration_url = "https://pqr.pkupuzzle.art/missing-abbreviations/"
    assert inspiration_url in resolved_map["help.details"]
    assert inspiration_url in resolved_map["game.rules"]
    assert inspiration_url in resolved_map["game.rules_markdown"]

    assert "<" not in resolved_map["game.rules_markdown"]
    assert ">" not in resolved_map["game.rules_markdown"]

    yaml_raw = _read_repo_file("src", "lang", "zh_hans", "missing_abbreviations.yaml")
    prompt_raw = _read_repo_file("src", "prompt", "missing_abbreviations", "system.md.jinja")
    rendered_prompt = await get_message("system", "missing_abbreviations/system.md.jinja")
    rendered_prompt_content = str(rendered_prompt["content"])

    for forbidden in ("北京大学", "P&KU", "谜协"):
        assert forbidden not in yaml_raw
        assert forbidden not in prompt_raw
        assert forbidden not in rendered_prompt_content
        for key, text in resolved_map.items():
            assert forbidden not in text, f"{key} 包含禁用词 {forbidden}"
