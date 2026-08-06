"""구조 해석기 — SPEC §8 골든 테스트가 중심이다.

§8 은 세 개의 수(1.8 / −1.5 / 총점 14.2)로 §5 스코어링 표 전체를 못박는다.
그 수가 맞으면 가드 정의·novelty 적용 범위·DP 목적함수가 전부 SPEC 대로라는 뜻이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.structure import dp, family, fingerprint, pipeline, registry, scoring  # noqa: E402
from core.structure import lexicon as lexicon_mod                          # noqa: E402
from core.structure.global_inner import nesting, ordinal                   # noqa: E402
from core.structure.global_outer import ladder as ladder_mod               # noqa: E402
from core.structure.global_outer import reg_score                          # noqa: E402
from core.structure.model import Block, ScopeStack                         # noqa: E402


# ===========================================================================
# §8.1 골든 입력
# ===========================================================================

GOLDEN = [
    "1. 총칙",
    "1.1 목적",
    "① 이 약관은…",
    "② 수탁자는…",
    "1.2 정의",
    "2. 운용",
    "2.1 운용방법 (1.1의 원칙을 준용)",
    "1. 국내채권",
]


def _blocks(lines) -> list[Block]:
    return [Block(idx=i, text=t, page=1) for i, t in enumerate(lines)]


@pytest.fixture(scope="module")
def golden():
    return pipeline.interpret(_blocks(GOLDEN), doc="golden")


def _by_surface(result, surface, block_idx):
    return next(c for c in result.candidates
                if c.surface == surface and c.block_idx == block_idx)


# ===========================================================================
# 관리소 — 어휘에 계층 지식이 없어야 한다 (§6)
# ===========================================================================

def test_registry_loads_signals():
    reg = registry.default()
    assert reg.by_role("proposer"), "제안자가 없습니다"
    assert reg.by_role("local_guard"), "국소 가드가 없습니다"


def test_no_signal_declares_level():
    """'몇 번째 레벨이냐' 는 어휘가 담지 않는다 — 레벨은 문서가 유도한다."""
    for s in registry.default().signals.values():
        for bad in registry.FORBIDDEN_ATTRS:
            assert not hasattr(s.module, bad), f"{s.id} 가 {bad} 를 노출합니다"


def test_signal_id_matches_filename():
    for s in registry.default().signals.values():
        assert s.id == s.module.__name__.rsplit(".", 1)[-1]


def test_guards_are_language_tagged():
    """조사 가드는 한국어 계열만 발화한다 (§3.2)."""
    reg = registry.default()
    ko = {s.id for s in reg.guards("ko")}
    en = {s.id for s in reg.guards("en")}
    assert "particle_ko" in ko
    assert "particle_ko" not in en


# ===========================================================================
# §8.2 S1 국소점수 기대값
# ===========================================================================

def test_golden_local_scores(golden):
    """c1~c7, c9 = +1.8 / c8 = −1.5 (§8.2)."""
    clean = [("1.", 0), ("1.1", 1), ("①", 2), ("②", 3),
             ("1.2", 4), ("2.", 5), ("2.1", 6), ("1.", 7)]
    for surface, block in clean:
        c = _by_surface(golden, surface, block)
        assert c.s == pytest.approx(1.8), f"{surface}@b{block} s={c.s} (기대 1.8)"

    c8 = _by_surface(golden, "1.1", 6)
    assert c8.s == pytest.approx(-1.5), f"c8 s={c8.s} (기대 −1.5)"
    assert c8.guards["block_pos"] == pytest.approx(scoring.BLOCK_INLINE)
    assert c8.guards["particle_ko"] == pytest.approx(scoring.PARTICLE_ATTACHED)
    assert c8.guards["particle_ko:referent"] == pytest.approx(scoring.PARTICLE_REFERENT)


def test_referent_penalty_needs_attached_particle(golden):
    """참조 서술어는 조사 부착일 때만 붙는다 — 아니면 c7 까지 감점돼 1.8 이 깨진다."""
    c7 = _by_surface(golden, "2.1", 6)
    assert "준용" in c7.text
    assert "particle_ko:referent" not in c7.guards
    assert c7.s == pytest.approx(1.8)


# ===========================================================================
# §8.3 S2 유도 사다리 기대값
# ===========================================================================

def test_golden_ladder(golden):
    """L0 = 점번호 depth1, L1 = 점번호 depth2, L2 = 원문자 (§8.3)."""
    lad = golden.ladder
    assert lad.level_of("dot_number:1") == 0
    assert lad.level_of("dot_number:2") == 1
    assert lad.level_of("circled") == 2


def test_golden_c8_and_c9_leave_the_normal_path(golden):
    """§8.3 은 c8·c9 를 둘 다 '미배정(문맥판정)' 으로 기대했다.

    단계 재배치 뒤 둘이 갈린다 — 최종 결과(§8.4: c8 기각, c9 활성)는 같지만 경로가 다르다.

        c8  계열 정합(S2)에서 확정 기각. 괄호 속 `1.1` 은 자기 계열 수열에서 리셋인데
            그 리셋을 정당화할 상위 경계가 같은 블록에 없다. 문맥판정까지 갈 것 없이
            여기서 끝난다 — 판정이 더 이르고 사유가 더 구체적이다.
        c9  미배정. `2.` 뒤의 `1.` 은 리셋인데 뒤가 안 이어져 문맥이 정해야 한다.
    """
    c8 = _by_surface(golden, "1.1", 6)
    c9 = _by_surface(golden, "1.", 7)
    assert not c8.survives and "리셋을 정당화할" in c8.family_note
    assert c9.survives and c9.unassigned
    assert {c.id for c in golden.candidates if c.unassigned} == {c9.id}


# ===========================================================================
# §8.4 S3 DP 결정 기대값 · §8.5 트리 · 총점 14.2
# ===========================================================================

def test_golden_dp_decisions(golden):
    """c1~c7 activate / c8 reject(mention) / c9 activate as 2.1 하위 (§8.4)."""
    for surface, block in [("1.", 0), ("1.1", 1), ("①", 2), ("②", 3),
                           ("1.2", 4), ("2.", 5), ("2.1", 6)]:
        assert _by_surface(golden, surface, block).activated, f"{surface}@b{block}"

    c8 = _by_surface(golden, "1.1", 6)
    assert not c8.activated, "괄호 속 1.1 은 mention 이다"

    c9 = _by_surface(golden, "1.", 7)
    assert c9.activated
    assert c9.activated_level == 2, f"c9 는 2.1(L1) 하위인 L2 에 앉아야 한다: {c9.decision_note}"


def test_golden_path_total_is_14_2(golden):
    """경로 총점 = 14.2 (§8.4). 8×1.8 − 0.2(c9 novelty)."""
    assert golden.stats["dp_total"] == pytest.approx(14.2), golden.stats


def test_golden_tree_shape(golden):
    """§8.5 최종 트리."""
    roots = golden.tree
    assert [r.surface for r in roots] == ["1.", "2."]
    total, unse = roots[0], roots[1]
    assert [c.surface for c in total.children] == ["1.1", "1.2"]
    assert [c.surface for c in total.children[0].children] == ["①", "②"]
    assert [c.surface for c in unse.children] == ["2.1"]
    assert [c.surface for c in unse.children[0].children] == ["1."]


def test_golden_audit_log_names_the_reason(golden):
    """§8.7 — 왜 버렸는지가 로그에 그대로 남는다."""
    c8 = _by_surface(golden, "1.1", 6)
    line = next(l for l in golden.audit_log if l.startswith(f"{c8.id}:"))
    assert "reject(mention)" in line and "-1.50" in line.replace("−", "-")


# ===========================================================================
# S2 계열 정합 — 사다리 없이 구조와 인용을 가른다
# ===========================================================================

def test_family_coherence_needs_no_ladder():
    """서수 비교는 계열 안에서만 일어난다 — 레벨을 몰라도 판정된다."""
    blocks = _blocks(["제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다"])
    reg, lex = registry.default(), lexicon_mod.default()
    cands = pipeline.s0_propose(blocks, reg, lex, "ko")
    pipeline.s1_score(cands, blocks, reg, lex, "ko")
    pipeline.s2_family(cands)              # 사다리를 만들기 **전**에 판정된다
    art = [c for c in cands if c.family_key == "kr_article"]
    assert all(c.survives for c in art)
    assert all(c.level is None for c in art), "이 단계에서는 레벨이 아직 없다"


def test_citation_with_same_surface_is_dropped_by_family():
    """조는 본문에서 제목과 같은 글자로 인용된다 — 계열 정합이 가른다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다",
        "제4조(기록) 금융위원회는 제1조, 제2조 또는 제3조에 따라 조치한다"]), doc="t")
    art = [c for c in r.candidates if c.family_key == "kr_article"]
    heads = [c for c in art if c.survives]
    assert [c.surface for c in heads] == ["제1조", "제2조", "제3조", "제4조"]
    assert len(art) > len(heads), "본문 속 인용이 후보로는 잡혀야 한다"


def test_leaping_citation_belongs_to_no_run():
    """`별표 3 → 9 → 22` — 어떤 연속 단위에도 안 이어지므로 전부 인용이다."""
    r = pipeline.interpret(_blocks([
        "부칙",
        "별표 3 제2호 나목의 위반 행위란 중 '법 제20조'를 '법 제20조제1항'으로 한다",
        "별표 9 제2호 도목의 위반 행위란 중 '법 제95조의2'를 '제97조'로 한다",
        "별표 22 제2호 타목 및 파목을 각각 삭제한다"]), doc="t")
    ann = [c for c in r.candidates if c.family_key.startswith("annex")]
    assert len(ann) == 3
    assert not [c for c in ann if c.survives], [c.family_note for c in ann]
    for c in ann:
        assert "연속 단위에도 이어지지 않습니다" in c.family_note, c.family_note


def test_citation_does_not_disturb_the_run():
    """`1조 2조 3조 [20조] 4조 5조` — 20조만 죽고 나머지는 그대로 이어진다.

    `prev` 하나로 걷던 이전 판은 20 으로 수열을 밀어(뒤가 죽거나) 3 에 묶어(앞이 죽어)
    둘 중 하나를 반드시 잃었다. 묶음을 여러 개 열어 두면 둘 다 산다.
    """
    r = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다",
        "제20조에 따르면 다음과 같이 처리한다",
        "제4조(범위) 라", "제5조(기록) 마"]), doc="t")
    art = [c for c in r.candidates if c.family_key == "kr_article"]
    surv = [c.surface for c in art if c.survives]
    assert surv == ["제1조", "제2조", "제3조", "제4조", "제5조"], surv
    dead = next(c for c in art if not c.survives)
    assert dead.surface == "제20조"


def test_parsing_gap_opens_a_new_run():
    """② 가 파싱에서 빠져도 ③④⑤⑥ 이 새 묶음을 이뤄 살아남는다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) ① 가", "③ 다", "④ 라", "⑤ 마", "⑥ 바"]), doc="t")
    circ = [c for c in r.candidates if c.family_key == "circled"]
    surv = [c.surface for c in circ if c.survives]
    assert surv == ["①", "③", "④", "⑤", "⑥"], surv
    assert len({c.chain for c in circ if c.survives}) == 2, "① 과 ③~⑥ 은 다른 묶음이다"


def test_sections_reset_per_chapter_articles_do_not():
    """한국 법령 실측: 절은 장마다 리셋, 조는 문서 전체 통번호.

    둘 다 하나의 계열로 정상 인식돼야 한다 — 리셋 여부는 연속 단위의 개수로만 드러난다.
    """
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1절 목적", "제1조(목적) 가", "제2조(정의) 나",
        "제2절 적용", "제3조(적용) 다", "제4조(범위) 라",
        "제2장 운용", "제1절 방법", "제5조(방법) 마", "제6조(제한) 바",
        "제2절 보고", "제7조(보고) 사", "제8조(검사) 아",
    ]), doc="t")
    jeol = [c for c in r.candidates if c.family_key == "kr_절" and c.survives]
    art = [c for c in r.candidates if c.family_key == "kr_article" and c.survives]
    assert [c.ordinal[0] for c in jeol] == [1, 2, 1, 2]
    assert len({c.chain for c in jeol}) == 2, "절은 장마다 리셋 → 연속 단위 2개"
    assert [c.ordinal[0] for c in art] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len({c.chain for c in art}) == 1, "조는 통번호 → 연속 단위 1개"


def test_ascending_citation_needs_position_not_just_ordinal():
    """오름차순 인용은 서수만으로 못 잡는다 — 위치가 잡는다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나",
        "제3조(적용) 「자본시장법」 제161조 및 「보험업법」 제336조를 준용한다"]), doc="t")
    surf = {c.surface for c in r.candidates
            if c.family_key == "kr_article" and c.survives}
    assert surf == {"제1조", "제2조", "제3조"}, surf


def test_inline_first_paragraph_survives():
    """`제8조(…) ① …` 의 ① 은 블록 중간이지만 진짜 구조다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) ① 가 ", "② 나", "제2조(정의) ① 다", "② 라"]), doc="t")
    circ = [c for c in r.candidates if c.family_key == "circled"]
    inline = [c for c in circ if c.offset > 0]
    assert inline and all(c.survives for c in inline), \
        "조 제목 줄에 붙어 온 제1항이 죽으면 안 된다"


def test_reg_score_is_not_diluted_by_citations():
    """등재점수가 인용 개수에 깎이지 않는다 (계열 정합이 먼저 걸렀으므로)."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다", "제4조(범위) 라",
        "제5조(기록) 제1조, 제2조, 제3조, 제4조에 따라 처리한다"]), doc="t")
    surv = [c for c in r.candidates if c.family_key == "kr_article" and c.survives]
    assert reg_score.score("kr_article", surv) >= scoring.REG_SCORE_MIN
    assert r.ladder.level_of("kr_article") is not None, "조가 사다리에 올라야 한다"


def test_reset_alignment_is_the_primary_nesting_evidence():
    """장 경계에서 조가 리셋되면 조는 장 아래 — 1표 차 판정이 아니다.

    리셋이 **2회 이상** 관측돼야 증거로 쓴다(`MIN_RESET_TOTAL`). 1회짜리 리셋은
    그 한 구간 안의 모든 계열이 부모 후보가 되어 판별력이 없다(절 실측).
    """
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다",
        "제2장 운용", "제1조(방법) 라", "제2조(제한) 마", "제3조(보고) 바",
        "제3장 감독", "제1조(보고) 사", "제2조(검사) 아", "제3조(제재) 자",
    ]), doc="t")
    lv = r.ladder.level_of
    assert lv("kr_장") is not None and lv("kr_article") is not None
    assert lv("kr_장") < lv("kr_article"), r.ladder.dump()
    assert any("리셋 정렬" in n for n in r.ladder.notes), r.ladder.notes


def test_single_reset_is_not_evidence():
    """리셋 1회로는 부모를 정하지 않는다 — 그 구간 안의 모든 계열이 후보가 된다."""
    from core.structure.global_outer import ladder as lad
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 운용", "제1조(방법) 다", "제2조(제한) 라",
    ]), doc="t")
    surv = lambda k: [c for c in r.candidates if c.family_key == k and c.survives]
    aligned, total = lad.reset_alignment(surv("kr_장"), surv("kr_article"))
    assert (aligned, total) == (1, 1)
    assert not any("리셋 정렬" in n for n in r.ladder.notes), r.ladder.notes


# ===========================================================================
# 사다리 결함이 시끄럽게 보고되는가
# ===========================================================================

def test_cycle_break_is_reported_loudly():
    """순환을 만나면 층이 이름 순으로 정해진다 — 그 사실이 반드시 남아야 한다."""
    from core.structure.global_outer import ladder as lad
    layers, broken = lad._toposort(["a", "b", "c"], {("a", "b"), ("b", "c"), ("c", "a")})
    assert broken, "순환을 끊었는데 보고하지 않았다"
    cycles = lad._find_cycles(["a", "b", "c"], {("a", "b"), ("b", "c"), ("c", "a")})
    assert cycles and cycles[0][0] == cycles[0][-1]


def test_ladder_defects_lower_the_fitness_score():
    """사다리 결함이 적합도에 반영된다 (§4 S5)."""
    from core.structure.model import Ladder, Rung
    clean = Ladder(rungs=[Rung(level=0, families=["a"]), Rung(level=1, families=["b"])],
                   n_pairs=1)
    broken = Ladder(rungs=[Rung(level=0, families=["a"]), Rung(level=1, families=["b"])],
                    n_pairs=1, cycle_broken=["b"], unordered_pairs=["a/b"],
                    unregistered=["c"])
    q_clean, p_clean = pipeline.ladder_quality(clean)
    q_broken, p_broken = pipeline.ladder_quality(broken)
    assert q_clean == 1.0 and not p_clean
    assert q_broken < q_clean and len(p_broken) == 3


def test_root_flattens_to_coordinate_convention():
    """`level` 은 section_id 를 만든다 — 좌표 규약을 밖에서 명시할 수 있어야 한다."""
    body = ["제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
            "제2장 운용", "제3조(방법) 다", "제4조(제한) 라"]
    deep = pipeline.interpret(_blocks(body), doc="t")
    flat = pipeline.interpret(_blocks(body), doc="t", root="kr_article")
    assert deep.ladder.level_of("kr_장") < deep.ladder.level_of("kr_article")
    assert flat.ladder.level_of("kr_장") == 0
    assert flat.ladder.level_of("kr_article") == 0
    assert "kr_장" in flat.ladder.flattened


# ===========================================================================
# 잔여 — 최선과 차선의 차로 잰다
# ===========================================================================

def test_anchor_rejection_does_not_pollute_the_sequence():
    """위치가 아니라고 한 것은 수열 위치를 건드리면 안 된다.

    법령 머리글 `[시행 2026. 1. 2.] … 2025. 10. 1.,` 의 날짜가 점번호로 잡히는데,
    이걸로 수열을 10 까지 밀면 그 뒤 호 6~10 이 통째로 죽는다(KSB 실측).
    """
    r = pipeline.interpret(_blocks([
        "1. 가나다", "2. 라마바", "3. 사아자", "4. 차카타", "5. 파하",
        "[시행 2026. 1. 2.] [법률 제21065호, 2025. 10. 1., 타법개정]",
        "6. 거너더", "7. 러머버", "8. 서어저"]), doc="t")
    dn = [c for c in r.candidates if c.family_key == "dot_number:1"]
    surv = [c.surface for c in dn if c.survives]
    assert surv == ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8."], surv


# ===========================================================================
# 잔여 — 신호가 서로 모순되는 후보를 모은다
# ===========================================================================

def test_residual_collects_guard_vs_run_conflict():
    """가드는 확실한 헤더라는데 계열 정합이 인용이라고 하면 잔여다."""
    r = pipeline.interpret(_residual_doc(), doc="t")
    conflict = [c for c in r.candidates if not c.survives and c.s >= scoring.CONFLICT_S]
    assert conflict, "제5조·제7조는 가드 만점인데 어떤 묶음에도 안 이어진다"
    assert any("가드↔수열" in x for x in r.residual), r.residual


def test_residual_prompt_carries_the_source_line():
    """LLM 배치 1콜에 던질 형태 — 후보마다 원문이 붙는다."""
    r = pipeline.interpret(_residual_doc(), doc="t.pdf")
    p = pipeline.residual_prompt(r)
    assert "t.pdf" in p and "원문:" in p and "제5조" in p


def test_deterministic_certainties_are_not_residual():
    """결정론이 확신한 것은 LLM 에 가지 않는다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다", "제4조(범위) 라"]), doc="t")
    assert not r.residual, r.residual


# ===========================================================================
# 힌트 주입 — 사람이 아는 것을 넣는 통로
# ===========================================================================

def test_families_restricts_the_vocabulary():
    body = ["1. 총칙", "2. 운용", "① 첫째", "② 둘째"]
    full = pipeline.interpret(_blocks(body), doc="t")
    narrow = pipeline.interpret(_blocks(body), doc="t", families=["dot_number"])
    assert {c.family for c in full.candidates} > {c.family for c in narrow.candidates}
    assert all(c.family == "dot_number" for c in narrow.candidates)


def test_partial_order_pins_a_thin_pair():
    """증거가 얇아 못 정하는 쌍에 한 줄 찍어 준다."""
    body = ["제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
            "제2장 운용", "제3조(방법) 다", "제4조(제한) 라"]
    pinned = pipeline.interpret(_blocks(body), doc="t",
                                partial_order=[("kr_장", "kr_article")])
    assert pinned.ladder.level_of("kr_장") < pinned.ladder.level_of("kr_article")
    assert any("(지정)" in n for n in pinned.ladder.notes), pinned.ladder.notes


def test_ladder_hint_skips_induction():
    body = ["1. 총칙", "1.1 목적", "① 가", "② 나", "1.2 정의", "2. 운용", "2.1 방법"]
    r = pipeline.interpret(_blocks(body), doc="t",
                           ladder_hint=[["dot_number:1"], ["dot_number:2"], ["circled"]])
    assert [r.ladder.level_of(k) for k in
            ("dot_number:1", "dot_number:2", "circled")] == [0, 1, 2]
    assert any("힌트로 세웠습니다" in n for n in r.ladder.notes)
    assert not r.ladder.cycle_broken and not r.ladder.unordered_pairs


def test_ladder_hint_still_reports_disagreement():
    """힌트를 줘도 관측은 돈다 — 어긋나면 알려야 한다."""
    body = ["1. 총칙", "1.1 목적", "① 가", "② 나", "1.2 정의", "2. 운용", "2.1 방법"]
    r = pipeline.interpret(_blocks(body), doc="t",
                           ladder_hint=[["circled"], ["dot_number:1"], ["dot_number:2"]])
    assert any("힌트와 관측이 어긋납니다" in n for n in r.ladder.notes), r.ladder.notes


def test_ladder_hint_flags_unexpected_family():
    """힌트에 없는데 발화한 계열은 시끄럽게 남는다."""
    r = pipeline.interpret(_blocks(
        ["1. 총칙", "2. 운용", "① 가", "② 나", "③ 다"]), doc="t",
        ladder_hint=[["dot_number:1"]])
    assert any("힌트에 없는데 발화한 계열" in n for n in r.ladder.notes), r.ladder.notes
    assert "circled" in r.ladder.unregistered


def test_residual_uses_decision_margin_not_raw_score():
    """블록 중간의 깨끗한 제1항(s=+0.30)은 애매하지 않다 — 잔여가 아니다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) ① 가", "② 나", "제2조(정의) ① 다", "② 라"]), doc="t")
    inline = [c for c in r.candidates
              if c.family_key == "circled" and c.offset > 0 and c.activated]
    assert inline
    for c in inline:
        assert c.decision_margin == pytest.approx(abs(c.s))
    assert not any("circled" in x for x in r.residual), r.residual


# ===========================================================================
# §8.6 S4 / S5
# ===========================================================================

def test_golden_fitness_passes_with_zero_llm(golden):
    assert golden.fitness_passed, golden.stats
    assert golden.fitness_score >= scoring.FITNESS_T


def test_singleton_does_not_freeze_a_frame(golden):
    """fingerprint 최초 → 문서결과 저장, frame freeze 안 함 (§8.6, §7)."""
    assert golden.stats["fingerprint_count"] == 1
    assert golden.stats["may_freeze"] is False
    assert golden.tier == fingerprint.WARM


def test_frame_freezes_on_repeat(tmp_path):
    """같은 fingerprint 가 FREEZE_AT 만큼 쌓이면 hot 승격 (§7)."""
    ledger = fingerprint.Ledger.load(tmp_path / "ledger.json")
    a = pipeline.interpret(_blocks(GOLDEN), doc="a.pdf", ledger=ledger)
    b = pipeline.interpret(_blocks(GOLDEN), doc="b.pdf", ledger=ledger)
    assert a.tier == fingerprint.WARM and not a.stats["may_freeze"]
    assert b.tier == fingerprint.HOT and b.stats["may_freeze"]
    assert a.fingerprint.key() == b.fingerprint.key()


# ===========================================================================
# 전역 정합성 — 안쪽 (§3.3, §5.2)
# ===========================================================================

def test_nesting_forbids_orphan_level():
    empty = ScopeStack.empty(3)
    assert nesting.check(0, empty) == nesting.OK
    assert nesting.check(2, empty) == nesting.FORBID


def test_nesting_allows_skipped_level():
    """제2조(정의)는 항 없이 곧바로 1./가. 로 간다 — 층 건너뜀은 금지가 아니다."""
    stack = ScopeStack.empty(4).activate(0, (2,))
    assert nesting.check(2, stack) == nesting.OK


def test_ordinal_penalises_regression_and_gap():
    stack = ScopeStack.empty(2).activate(0, (3,))
    assert ordinal.check(0, (2,), stack)[0] == pytest.approx(scoring.ORDINAL_REGRESS)
    assert ordinal.check(0, (5,), stack)[0] == pytest.approx(scoring.ORDINAL_GAP)
    assert ordinal.check(0, (4,), stack)[0] == 0.0


def test_reset_is_not_a_regression():
    """장이 바뀌면 하위 스코프가 닫히므로 조 번호 리셋은 애초에 역행이 아니다.

    이 성질이 깨지면 문서가 반 토막 난 채 번호는 완벽히 연속인 결과가 나온다 —
    적합도 게이트조차 알아채지 못하는 조용한 실패다.
    """
    stack = ScopeStack.empty(2).activate(0, (1,)).activate(1, (5,))
    assert stack.last[1] == (5,)
    stack = stack.activate(0, (2,))          # 다음 장
    assert stack.last[1] is None, "상위가 열리면 하위 스코프가 닫혀야 한다"
    assert ordinal.check(1, (1,), stack)[0] == 0.0


def test_branch_article_ordinal_is_lexicographic():
    """제10조 → 제10조의2 → 제11조 이 단조증가여야 한다."""
    stack = ScopeStack.empty(1).activate(0, (10,))
    assert ordinal.check(0, (10, 2), stack)[0] == 0.0
    stack = stack.activate(0, (10, 2))
    assert ordinal.check(0, (11,), stack)[0] == 0.0


# ===========================================================================
# 제안자 — 표면만 안다
# ===========================================================================

def test_korean_article_and_branch():
    res = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나", "제2조의2(추가) 다", "제3조(적용) 라"]),
        doc="t")
    surfaces = [c.surface for c in res.candidates if c.family == "kr_article"]
    assert "제2조의2" in surfaces
    branch = next(c for c in res.candidates if c.surface == "제2조의2")
    assert branch.ordinal == (2, 2)


def test_mention_in_running_text_is_scored_down():
    """`제3장의 규정에 따라` — 조사 + 참조 서술어."""
    res = pipeline.interpret(_blocks([
        "제1장 총칙", "제2장 운용", "제3장 해지",
        "앞의 제3장의 규정에 따라 처리한다"]), doc="t")
    mention = next(c for c in res.candidates
                   if c.block_idx == 3 and c.surface == "제3장")
    assert mention.s < 0, mention.guards
    assert not mention.activated


def test_circled_range_covers_16_to_20():
    lex = lexicon_mod.default()
    assert lex.numerals.read("⑯") == 16
    assert lex.numerals.read("⑳") == 20


def test_determinism():
    a = pipeline.interpret(_blocks(GOLDEN), doc="x").dump()
    b = pipeline.interpret(_blocks(GOLDEN), doc="x").dump()
    assert a == b


# ===========================================================================
# S5b 잔여 해소 — 문서당 배치 1콜
# ===========================================================================

class _FakeLLM:
    """호출 횟수와 프롬프트를 기록하는 가짜 모델."""

    def __init__(self, verdicts):
        self.verdicts, self.calls, self.prompts = verdicts, 0, []

    def structured(self, kind, system, user, schema, **kw):
        self.calls += 1
        self.prompts.append(user)
        return {"verdicts": self.verdicts}


def _residual_doc():
    """빠진 번호일 수 있는 조가 둘인 문서 — 잔여가 2건 나온다.

    `5` 와 `7` 은 각각 혼자라 어떤 묶음에도 안 이어지지만, 가까운 묶음(1~3)과 번호 차가
    작아 **빠진 번호일 수 있다** → 애매. 멀리 떨어진 번호(50 같은)는 잔여가 아니다.
    """
    return _blocks(["제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다",
                    "제5조(범위) 라", "제7조(준용) 마"])


def test_no_residual_means_no_llm_call():
    """잔여가 0건이면 호출 자체가 없다 (§4 S5 '대개 0콜')."""
    llm = _FakeLLM([])
    r = pipeline.interpret(_blocks(["제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다"]),
                           doc="t", llm=llm)
    assert not r.residual and llm.calls == 0


def test_residual_is_resolved_in_one_batch_call():
    """후보가 여럿이어도 **한 번**만 부른다."""
    base = pipeline.interpret(_residual_doc(), doc="t")
    ids = [x.split()[1] for x in base.residual]
    assert len(ids) >= 2
    llm = _FakeLLM([{"id": i, "verdict": "structure", "reason": "조문 제목"} for i in ids])
    r = pipeline.interpret(_residual_doc(), doc="t", llm=llm)
    assert llm.calls == 1, "per-후보 루프가 아니라 배치 1콜이어야 한다"
    assert r.stats["llm"]["asked"] == len(ids)


def test_structure_verdict_revives_the_candidate():
    base = pipeline.interpret(_residual_doc(), doc="t")
    cid = base.residual[0].split()[1]
    llm = _FakeLLM([{"id": cid, "verdict": "structure", "reason": "조문 제목이다"}])
    r = pipeline.interpret(_residual_doc(), doc="t", llm=llm)
    c = next(x for x in r.candidates if x.id == cid)
    assert c.survives and "LLM 판정: 구조" in c.family_note
    assert r.stats["llm"]["changed"] >= 1


def test_mention_verdict_kills_a_surviving_candidate():
    """살아 있던 후보에 인용 판정이 오면 죽는다.

    [손해활성]·[근소차] 잔여는 실제 문서에서만 드물게 나오므로(작은 픽스처에서는
    결정론이 전부 확신한다), 적용 로직만 `resolve()` 를 직접 불러 확인한다.
    """
    from core.structure import resolve as resolve_mod

    r = pipeline.interpret(_blocks(
        ["제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다"]), doc="t")
    victim = next(c for c in r.candidates if c.survives)
    r.residual = [f"[손해활성] {victim.id} {victim.family_key} '{victim.surface}' "
                  f"@블록{victim.block_idx} p1 — 전이 -1.20"]

    llm = _FakeLLM([{"id": victim.id, "verdict": "mention", "reason": "인용이다"}])
    out = resolve_mod.resolve(r, llm, rebuild=False)
    assert llm.calls == 1 and out.changed == 1
    assert not victim.survives and "LLM 판정: 인용" in victim.family_note


def test_verdict_change_rebuilds_the_ladder_and_tree():
    """판정이 바뀌면 사다리·DP·트리를 다시 세운다 — 트리만 손보면 앞뒤가 안 맞는다."""
    from core.structure import resolve as resolve_mod

    r = pipeline.interpret(_blocks(
        ["제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다", "제4조(범위) 라"]), doc="t")
    before = [n.surface for n in r.nodes()]
    victim = next(c for c in r.candidates if c.survives and c.surface == "제3조")
    r.residual = [f"[근소차] {victim.id} {victim.family_key} '{victim.surface}' "
                  f"@블록{victim.block_idx} p1 — 마진 0.10"]
    llm = _FakeLLM([{"id": victim.id, "verdict": "mention", "reason": "인용"}])
    resolve_mod.resolve(r, llm, rebuild=True)
    after = [n.surface for n in r.nodes()]
    assert "제3조" in before and "제3조" not in after, (before, after)
    assert any("LLM 배치 1콜" in line for line in r.audit_log)


def test_hallucinated_id_is_discarded():
    """후보 목록에 없는 id 는 버린다 — 지어낼 자리를 주지 않는다."""
    llm = _FakeLLM([{"id": "c9999", "verdict": "structure", "reason": "지어낸 것"}])
    r = pipeline.interpret(_residual_doc(), doc="t", llm=llm)
    assert r.stats["llm"]["ignored"] == ["c9999"]
    assert r.stats["llm"]["changed"] == 0


def test_llm_failure_keeps_deterministic_verdict():
    class _Dead:
        calls = 0

        def structured(self, *a, **k):
            _Dead.calls += 1
            return None

    base = pipeline.interpret(_residual_doc(), doc="t")
    r = pipeline.interpret(_residual_doc(), doc="t", llm=_Dead())
    assert [c.survives for c in r.candidates] == [c.survives for c in base.candidates]
    assert any("잔여 해소 실패" in w for w in r.warnings)


def test_prompt_only_contains_residual_candidates():
    """확신한 것은 프롬프트에 들어가지 않는다 — 물음이 좁아야 한다."""
    base = pipeline.interpret(_residual_doc(), doc="t")
    ids = {x.split()[1] for x in base.residual}
    llm = _FakeLLM([])
    pipeline.interpret(_residual_doc(), doc="t", llm=llm)
    prompt = llm.prompts[0]
    for c in base.candidates:
        if c.id not in ids:
            assert f" {c.id} " not in prompt


def test_llm_off_path_is_deterministic():
    a = pipeline.interpret(_residual_doc(), doc="t").dump()
    b = pipeline.interpret(_residual_doc(), doc="t").dump()
    assert a == b


def test_adjudicated_candidate_is_not_asked_twice():
    """배치가 판정한 후보는 다시 잔여로 올라오지 않는다 — 목록이 수렴해야 한다."""
    from core.structure import resolve as resolve_mod

    r = pipeline.interpret(_residual_doc(), doc="t")
    ids = [x.split()[1] for x in r.residual]
    assert ids
    llm = _FakeLLM([{"id": i, "verdict": "mention", "reason": "인용"} for i in ids])
    resolve_mod.resolve(r, llm, rebuild=True)
    assert all(c.llm_verdict for c in r.candidates if c.id in ids)
    assert not [x for x in r.residual if x.split()[1] in ids], r.residual



# ===========================================================================
# 들여쓰기 — 계층의 기하 증거
# ===========================================================================

def _boxed(lines):
    """(text, left_x) 목록 → 블록. 페이지 폭은 600 으로 고정."""
    return [Block(idx=i, text=t, page=1, bbox=[x, 700 - i * 20, 560, 690 - i * 20])
            for i, (t, x) in enumerate(lines)]


def test_indent_orders_sparse_families():
    """절 6건처럼 성긴 계열은 리셋·덮음·사이-끼임이 다 침묵한다 — 들여쓰기가 잡는다."""
    from core.structure.global_outer import indent

    blocks = _boxed([("제1장 총칙", 30), ("제1절 목적", 50),
                     ("제1조(목적) 가", 70), ("제2조(정의) 나", 70),
                     ("제2장 운용", 30), ("제2절 방법", 50),
                     ("제3조(방법) 다", 70), ("제4조(제한) 라", 70)])
    r = pipeline.interpret(blocks, doc="t")
    lv = r.ladder.level_of
    assert lv("kr_장") < lv("kr_절") < lv("kr_article"), r.ladder.dump()
    assert any("들여쓰기" in n for n in r.ladder.notes), r.ladder.notes


def test_indent_stays_silent_on_a_tie():
    """같은 들여쓰기면 간선을 놓지 않는다 — 다른 증거에 넘긴다."""
    from core.structure.global_outer import indent
    from core.structure.model import Candidate

    same = lambda fam, n: [Candidate(id=f"{fam}{i}", family=fam, page=1,
                                     bbox=[50, 0, 500, 0], offset=0, block_idx=i)
                           for i in range(n)]
    w = {1: 600.0}
    assert indent.order(same("a", 4), same("b", 4), w) is None


def test_indent_ignores_mid_block_markers():
    """블록 중간 마커는 들여쓰기를 말하지 않는다 — 블록의 왼쪽 끝이 자기 위치가 아니다."""
    from core.structure.global_outer import indent
    from core.structure.model import Candidate

    mid = [Candidate(id=f"x{i}", family="f", page=1, bbox=[50, 0, 500, 0],
                     offset=20, block_idx=i) for i in range(4)]
    assert indent.left(mid, {1: 600.0}) is None


# ===========================================================================
# 가지조(제N조의M) — 다음 번호 규칙
# ===========================================================================

def test_succession_handles_branch_numbering():
    """한국 법령은 조를 삭제하지 않고 사이에 끼워 넣는다 — 자릿수가 섞인다."""
    from core.structure.family.succession import follows

    assert follows((16, 2), (16,)), "본조 → 첫 가지조"
    assert follows((16, 3), (16, 2)), "가지조 → 다음 가지조"
    assert follows((17,), (16, 2)), "가지조 → 다음 본조"
    assert follows((17,), (16,)), "본조끼리"

    assert not follows((16, 4), (16,)), "가지는 의2 부터 — 의4 로 건너뛸 수 없다"
    assert not follows((18,), (16, 2)), "본조를 건너뛸 수 없다"
    assert not follows((16, 2), (17,)), "역행"


def test_branch_article_stays_in_the_run():
    """`제16조 → 제16조의2 → 제17조` 가 하나의 연속 단위여야 한다.

    자릿수만 비교하던 규칙에서는 가지조가 어떤 묶음에도 못 붙어 인용으로 오판됐다
    (실측 KSB: 제16조의2·제21조의2 가 가드 만점인데 탈락).
    """
    r = pipeline.interpret(_blocks([
        "제15조(적용) 가", "제16조(범위) 나", "제16조의2(특례) 다",
        "제16조의3(예외) 라", "제17조(보고) 마"]), doc="t")
    art = [c for c in r.candidates if c.family_key == "kr_article" and c.survives]
    assert [c.surface for c in art] == [
        "제15조", "제16조", "제16조의2", "제16조의3", "제17조"], [c.surface for c in art]
    assert len({c.chain for c in art}) == 1, "전부 하나의 연속 단위여야 한다"


def test_branch_citation_still_dies():
    """부칙의 타법개정 문구는 가지 표기여도 인용이다 — 이어지는 것이 없다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) 가", "제2조(정의) 나", "제3조(적용) 다",
        "제22조의2(준용) 라"]), doc="t")
    dead = [c for c in r.candidates
            if c.family_key == "kr_article" and not c.survives]
    assert [c.surface for c in dead] == ["제22조의2"], [c.surface for c in dead]


# ===========================================================================
# 잔여 — 멀리 떨어진 인용은 애매하지 않다
# ===========================================================================

def test_distant_citation_is_not_residual():
    """`50. 「금융소비자 보호에 관한 법률」` 은 결정론이 확신한다 — LLM 에 안 묻는다.

    실측(KSB-D): 애매한 것은 인접 묶음과 번호 차 0, 인용은 13~48 로 갈린다.
    """
    r = pipeline.interpret(_blocks([
        "1. 가나다", "2. 라마바", "3. 사아자",
        "50. 「금융소비자 보호에 관한 법률」"]), doc="t")
    far = next(c for c in r.candidates
               if c.family_key == "dot_number:1" and c.surface == "50.")
    assert not far.survives
    assert not [x for x in r.residual if far.id in x], r.residual


def test_near_miss_is_residual():
    """가까운 번호는 빠진 번호일 수 있다 — 애매하므로 묻는다."""
    r = pipeline.interpret(_blocks([
        "1. 가나다", "2. 라마바", "3. 사아자", "5. 차카타"]), doc="t")
    near = next(c for c in r.candidates
                if c.family_key == "dot_number:1" and c.surface == "5.")
    assert not near.survives
    assert [x for x in r.residual if near.id in x], r.residual


def test_composite_citation_needs_a_block_opener():
    """`3) … 14. 1) 에 따른` — `1)` 이 `14.`(중간 마커)에 기대 통과하면 안 된다."""
    r = pipeline.interpret(_blocks([
        "1) 첫째", "2) 둘째",
        "3) 임직원등은 해외자산에 투자하는 경우에는 14. 1) 에 따른 설명을 한다"]), doc="t")
    leaked = [c for c in r.candidates
              if c.block_idx == 2 and c.offset > 0 and c.survives]
    assert not leaked, [(c.surface, c.family_note) for c in leaked]


# ===========================================================================
# 제목 — 구역의 이름 (좌표와 별개)
# ===========================================================================

def test_title_from_parenthetical():
    """`제7조(금융소비자의 기본적 권리)` — 마커 직후 괄호가 이름이다."""
    r = pipeline.interpret(_blocks([
        "제1조(목적) 이 법은 금융소비자의 권익 증진을 위하여 …",
        "제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.",
        "제3조(금융소비자의 기본적 권리) 금융소비자는 다음 각 호의 권리를 가진다."]), doc="t")
    got = {n.surface: n.title for n in r.nodes()}
    assert got == {"제1조": "목적", "제2조": "정의",
                   "제3조": "금융소비자의 기본적 권리"}, got


def test_title_from_short_tail():
    """`제1장 총칙` — 꼬리가 짧고 종결부호가 없으면 그대로 이름이다."""
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 금융상품판매업자등의 등록 등", "제3조(등록) 다", "제4조(요건) 라"]), doc="t")
    got = {n.surface: n.title for n in r.nodes() if n.family == "kr_장"}
    assert got == {"제1장": "총칙", "제2장": "금융상품판매업자등의 등록 등"}, got


def test_title_stops_at_the_next_marker_in_the_same_block():
    """`제4장 … 제1절 …` 이 한 줄이면 각자 자기 이름만 가져간다."""
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 준수사항 제1절 영업행위 일반원칙", "제3조(기준) 다", "제4조(적용) 라",
        "제2절 유형별 준수사항", "제5조(적합성) 마", "제6조(적정성) 바",
    ]), doc="t", partial_order=[("kr_장", "kr_절"), ("kr_절", "kr_article")])
    got = {n.surface: n.title for n in r.nodes() if n.family in ("kr_장", "kr_절")}
    assert got["제2장"] == "준수사항", got
    assert got["제1절"] == "영업행위 일반원칙", got


def test_body_line_has_no_title():
    """`1. '금융상품'이란 …` 은 이름이 없다 — 억지로 첫 구절을 자르지 않는다."""
    r = pipeline.interpret(_blocks([
        "1. '금융상품'이란 다음 각 목의 어느 하나에 해당하는 것을 말한다.",
        "2. '금융상품판매업'이란 이익을 얻을 목적으로 계속적으로 하는 행위를 말한다.",
        "3. '금융소비자'란 금융상품에 관한 계약의 상대방을 말한다."]), doc="t")
    for n in r.nodes():
        assert not n.title, (n.surface, n.title)
        assert "이름 없음" in n.title_reason


def test_applied_hints_are_recorded():
    """힌트는 시스템 규칙이 아니라 이 문서에 대한 입력 — 결과에 남아야 한다."""
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 운용", "제3조(방법) 다", "제4조(제한) 라"]), doc="t",
        partial_order=[("kr_장", "kr_article")], root="kr_article")
    assert r.applied["partial_order"] == ["kr_장>kr_article"]
    assert r.applied["root"] == "kr_article"
    assert r.applied["llm"] is False


# ===========================================================================
# 불릿 — 번호 없는 문서의 마커 (proposers/bullet.py)
# ===========================================================================

def test_bullet_opens_a_section_without_an_ordinal():
    """`■` `·` `▶` 는 서수가 없어도 구역을 연다 — 번호만 마커인 것이 아니다."""
    r = pipeline.interpret(_blocks([
        "■ 신탁기간 변경", "계약시작일 21 년 월 일",
        "■ 운용지시 변경", "신탁자금 운용방법",
        "■ 기타 변경내용", "구분 변경 전 변경 후"]), doc="t")
    opened = [n.surface for n in r.nodes() if n.family == "bullet_■"]
    assert len(opened) == 3, [c.surface for c in r.candidates]
    assert all(c.ordinal is None for c in r.candidates if c.family == "bullet_■")


def test_bullet_glyphs_are_separate_families():
    """`■` 와 `·` 는 같은 문서에서 다른 깊이로 쓰인다 — 한 칸에 얹히면 안 된다."""
    r = pipeline.interpret(_blocks([
        "■ 운용지시 변경", "· 세부 운용지시", "내용 가",
        "■ 기타 변경내용", "· 기타 특약사항", "내용 나"]), doc="t")
    fams = {c.family for c in r.candidates if c.family.startswith("bullet")}
    assert fams == {"bullet_■", "bullet_·"}, fams


def test_bullet_variants_fold_to_one_family():
    """`◼` 는 `■` 다 — 판본이 글꼴만 바꿔도 사다리가 달라지면 안 된다."""
    r = pipeline.interpret(_blocks([
        "■ 하나", "내용 가", "◼ 둘", "내용 나", "▪ 셋", "내용 다"]), doc="t")
    assert {c.family for c in r.candidates if c.family.startswith("bullet")} == {"bullet_■"}


def test_checkbox_is_not_a_bullet():
    """`□ 우편` 은 선택지다. 이걸 마커로 세우면 양식 한 쪽에서 가짜 후보가 쏟아진다."""
    r = pipeline.interpret(_blocks([
        "□ 우편 □ 이메일", "[ ] 통지 생략 [ ] 통지 요청",
        "■ 진짜 마커", "내용", "■ 또 하나", "내용"]), doc="t")
    surfaces = [c.surface for c in r.candidates if c.family.startswith("bullet")]
    assert "□" not in surfaces and "[" not in surfaces, surfaces


def test_middot_between_words_is_not_a_marker():
    """`우편·이메일` 의 가운뎃점은 낱말 구분자다 — 공백이 있어야 마커로 본다."""
    r = pipeline.interpret(_blocks([
        "수령처는 우편·이메일 중에서 고른다.",
        "· 진짜 마커", "내용", "· 또 하나", "내용"]), doc="t")
    hits = [c for c in r.candidates if c.family == "bullet_·"]
    assert all(c.block_idx != 0 for c in hits), [(c.block_idx, c.text) for c in hits]
