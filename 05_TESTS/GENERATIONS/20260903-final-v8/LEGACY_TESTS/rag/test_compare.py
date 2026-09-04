"""내규↔외규 비교기 — 값 비교(결정론)와 verdict 합성 (docs/COMPARE_INTERNAL_EXTERNAL.md).

값 비교의 세 조건(같은 종류·같은 축·지표 겹침)과 축별 방향, 그리고 "결정론이
확정한 쌍은 LLM 이 뒤집지 못한다"를 잠근다. 예시 수치는 예시 내규 v2 에 심어둔
검증 포인트(120% vs 100분의 150 · 500% vs 100% · 45일 vs 지체없이) 그대로다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import compare  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402


# ---------------------------------------------------------------- 값 추출
def test_quants_reads_ratio_axis_and_indicator():
    q = compare.quants("순자본비율이 100분의 120에 미달하는 경우 그 미달상태가 "
                       "해소될 때까지 새로운 장외파생상품의 매매를 중지한다")
    assert q and q[0]["종류"] == "비율" and q[0]["값"] == 1.2
    assert q[0]["축"] == "하한" and "순자본비율" in q[0]["지표"]


def test_quants_percent_and_deadline():
    q = compare.quants("순자본비율이 100%에 미달하는 경우 지체없이 보고하여야 한다")
    kinds = {(r["종류"], r["값"], r["축"]) for r in q}
    assert ("비율", 1.0, "하한") in kinds
    assert ("기한", 0.0, "상한") in kinds          # 지체없이 = 0일


def test_quants_period_upper():
    q = compare.quants("해당 분기 종료 후 45일 이내에 금융감독원장에게 보고한다")
    assert ("기한", 45.0, "상한") in {(r["종류"], r["값"], r["축"]) for r in q}


# ---------------------------------------------------------------- 쌍 방향
NAE_120 = "순자본비율이 100분의 120에 미달하는 경우 새로운 장외파생상품의 매매를 중지한다"
OE_150 = "순자본비율이 100분의 150에 미달하는 경우 새로운 장외파생상품의 매매를 중지할 것"


def test_lower_axis_relaxation_is_conflict_signal():
    """하한 축: 내규 120 < 외규 150 → 완화 (예시 t5s2-01)."""
    rows = compare.compare_quants(NAE_120, OE_150)
    assert rows and rows[0]["방향"] == "완화", rows
    assert rows[0]["내규"]["표기"] == "100분의 120"
    assert rows[0]["외규"]["표기"] == "100분의 150"


def test_lower_axis_strengthening_is_not_conflict():
    """하한 축: 내규 500% ≥ 외규 100% → 강화 — 보수적이면 부합 (예시 t5s2-04)."""
    rows = compare.compare_quants(
        "회사는 순자본비율을 100분의 500 이상으로 유지하는 것을 내부 관리목표로 한다",
        "순자본비율이 100%에 미달하는 경우 지체없이 보고하여야 한다")
    assert rows and all(r["방향"] == "강화" for r in rows), rows


def test_deadline_axis_45_days_vs_immediately():
    """기한(상한) 축: 45일 > 지체없이(0) → 완화 (예시 t5s2-03 의 구판 v1)."""
    rows = compare.compare_quants(
        "순자본비율이 100분의 100에 미달하는 경우 회사는 해당 분기 종료 후 45일 "
        "이내에 금융감독원장에게 보고한다",
        "순자본비율이 100%에 미달하는 경우 지체없이 이를 금융감독원장에게 "
        "보고하여야 한다")
    assert any(r["종류"] == "기한" and r["방향"] == "완화" for r in rows), rows


def test_different_indicator_is_not_paired():
    """지표가 다르면(총위험액 ↔ 순자본비율) 쌍이 아니다 — 억지 쌍 금지."""
    rows = compare.compare_quants(
        "총위험액을 자기자본의 100분의 35 이내로 관리한다",
        "순자본비율이 100분의 150에 미달하는 경우 매매를 중지할 것")
    assert rows == [], rows


def test_formula_article_pairs_by_consequence_window():
    """산식 조문(§166의2 — '순자본비율' 낱말 없음)은 결과 문구로 쌍이 잡힌다."""
    rows = compare.compare_quants(
        NAE_120,
        "영업용순자본에서 총위험액을 차감한 금액을 인가업무 단위별 자기자본을 "
        "합계한 금액으로 나눈 값이 100분의 150에 미달하는 경우에는 그 미달상태가 "
        "해소될 때까지 새로운 장외파생상품의 매매를 중지하고")
    assert rows and rows[0]["방향"] == "완화", rows


def test_parenthetical_insertion_does_not_break_pairing():
    """값과 술어 사이 괄호 삽입("(겸영금융투자업자의 경우에는 …)")은 결과창을
    끊지 못한다 — 실측 §166의2 원문 그대로."""
    rows = compare.compare_quants(
        "순자본비율이 100분의 120에 미달하는 경우 그 미달상태가 해소될 때까지 "
        "새로운 장외파생상품의 매매를 중지하고",              # 예시 내규 v2 원문
        "나눈 값이 100분의 150에 미달하는 경우(겸영금융투자업자의 경우에는 "
        "금융위원회가 정하여 고시하는 경우를 말한다)에는 그 미달상태가 해소될 "
        "때까지 새로운 장외파생상품의 매매를 중지하고")
    assert rows and rows[0]["방향"] == "완화", rows


def test_prefixed_indicator_is_a_different_indicator():
    """'영업용순자본비율 150%'(3종)는 '순자본비율 100%'(1종)의 짝이 아니다 —
    접미 관계 지표는 배제 (실측 t5s2-03 오판)."""
    rows = compare.compare_quants(
        "순자본비율이 100분의 100에 미달하는 경우 지체없이 보고한다",
        "3종 금융투자업자 : 영업용순자본비율이 150%에 미달하는 경우 보고하여야 한다")
    assert not [r for r in rows if r["종류"] == "비율"], rows


def test_pairs_are_deduped():
    """외규 조에 같은 표기가 여러 번 나와도 쌍은 한 번만."""
    rows = compare.compare_quants(
        NAE_120, OE_150 + " " + OE_150)
    assert len([r for r in rows if r["종류"] == "비율"]) == 1, rows


def test_different_axis_is_not_paired():
    """같은 지표라도 축이 다르면(이내 ↔ 미달) 쌍이 아니다."""
    rows = compare.compare_quants(
        "순자본비율 변동폭을 100분의 10 이내로 관리한다",
        "순자본비율이 100분의 150에 미달하는 경우 매매를 중지할 것")
    assert rows == [], rows


# ---------------------------------------------------------------- verdict 합성
class _FakeLLM:
    def __init__(self, pairs):
        self._pairs = pairs
        self.log = []

    def structured(self, kind, system, user, schema, **kw):
        if kind == "rag.compare":
            return {"pairs": self._pairs}
        return None


def _mini(monkeypatch, tmp_path):
    """내규 1문서·외규 1문서 색인 + 스코프 + 간선 하나."""
    from lawrag.core.rag.index import Index

    nae = ("n1", {"name": "세칙", "kind": "internal", "folder": "내규"},
           {"nodes": [{"id": 1, "parent": None, "level": 0, "surface": "제12조",
                       "title": "장외파생상품 거래", "page": 1, "span": [0, 1]}],
            "blocks": [{"idx": 0, "page": 1, "text": NAE_120, "kind": "text"}]})
    oe = ("o1", {"name": "자본시장법", "kind": "law"},
          {"nodes": [{"id": 1, "parent": None, "level": 0, "surface": "제166조의2",
                      "title": "장외파생상품의 매매 등", "page": 1, "span": [0, 1]}],
           "blocks": [{"idx": 0, "page": 1, "text": OE_150, "kind": "text"}]})
    oe2 = ("o2", {"name": "금융투자업규정", "kind": "admrul"},
           {"nodes": [{"id": 2, "parent": None, "level": 0, "surface": "제3-44조",
                       "title": "위험관리지침", "page": 2, "span": [0, 1]}],
            "blocks": [{"idx": 0, "page": 2,
                        "text": "위험관리지침은 내부 보고 및 승인체계를 정하여야 한다",
                        "kind": "text"}]})
    internal2 = ("n2", {"name": "다른세칙", "kind": "internal", "folder": "내규"},
                 {"nodes": [{"id": 1, "parent": None, "level": 0,
                              "surface": "제1조", "title": "목적", "page": 1,
                              "span": [0, 1]}],
                  "blocks": [{"idx": 0, "page": 1, "text": "목적 조문",
                              "kind": "text"}]})
    idx = Index.from_docs([nae, oe, oe2, internal2])
    idx._cross = ([{"src_doc": "n1", "src": 1, "dst_doc": "o1", "dst": 1,
                    "surface": "제166조의2", "hint": "자본시장법", "block": 0,
                    "via": "이름대조", "rel": "인용"}], [])
    monkeypatch.setenv("STRUCTURE_STORE", str(tmp_path))
    import lawrag.core.rag.scopes as scopes_mod
    monkeypatch.setattr(scopes_mod, "apply",
                        lambda idx0, scope, docs: (idx0.scoped(frozenset({"o1"}), scope)
                                                   if hasattr(idx0, "scoped")
                                                   else _scoped(idx0), {}))
    from lawrag.core.rag import legalclosure_runtime
    monkeypatch.setattr(legalclosure_runtime, "retrieve",
                        lambda *a, **k: ([], {
                            "strategy": "fixture", "selected": [],
                            "article_reachability": {"fixture": True},
                            "legal_annotations": {"rows": []},
                        }))
    return idx


def _scoped(idx):
    idx.scope = frozenset({"o1"})
    return idx


def test_compare_article_determinism_overrides_llm(monkeypatch, tmp_path):
    """값 비교가 '완화=상충'으로 확정하면 LLM 의 '부합'은 뒤집힌다."""
    idx = _mini(monkeypatch, tmp_path)
    llm = _FakeLLM([{"n": 1, "판정": "부합", "근거": "그럴듯한 소리", "인용": ""}])
    out = compare.compare_article(llm, idx, "n1", 1)
    assert out["verdict"] == "상충", out
    assert out["판정"][0]["결정론우선"] == "상충"
    assert out["값비교"] and out["값비교"][0]["방향"] == "완화"
    assert out["후보"][0]["via"] == "간선"


def test_compare_article_without_candidates_is_review(monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    idx._cross = ([], [])
    import lawrag.core.rag.vector as vector_mod
    monkeypatch.setattr(vector_mod, "search", lambda *a, **k: [])
    out = compare.compare_article(None, idx, "n1", 1)
    assert out["verdict"] == "재검토" and out["짝없음"], out


def test_legalclosure_candidate_keeps_origin_annotation_and_trace(monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    idx._cross = ([], [])
    from lawrag.core.rag import legalclosure_runtime
    section = Section(
        n=1, doc_id="o2", doc="금융투자업규정", node=2,
        path="제3-44조", page=2, kind="법률좌표폐쇄", matched="assertion-tree",
        text="위험관리지침은 내부 보고 및 승인체계를 정하여야 한다",
        legal_meta={"validity": {"status": "current"},
                    "requirement_spans": [{"kind": "의무", "surface": "정하여야 한다"}]})
    monkeypatch.setattr(legalclosure_runtime, "retrieve", lambda *a, **k: (
        [section], {"strategy": "fixture-legalclosure",
                    "selected": [{"doc_id": "o2", "node": 2,
                                  "origin": "assertion-tree"}],
                    "closure": [{"doc_id": "o2", "node": 2,
                                 "mandatory": True}],
                    "article_reachability": {"capture_sha256": "fixture"},
                    "legal_annotations": {"rows": [section.legal_meta]}}))

    out = compare.compare_article(
        _FakeLLM([{"n": 1, "판정": "부합", "근거": "승인체계를 정함", "인용": ""}]),
        idx, "n1", 1)
    assert out["후보"][0]["origin"] == "assertion-tree"
    assert out["후보"][0]["mandatory"] is True
    assert out["후보"][0]["legal_meta"]["validity"]["status"] == "current"
    assert out["검색"]["strategy"] == "fixture-legalclosure"
    assert out["검색"]["article_reachability"]["capture_sha256"] == "fixture"


def test_direct_reference_is_first_and_enriched_by_legalclosure(monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    from lawrag.core.rag import legalclosure_runtime
    section = Section(
        n=1, doc_id="o1", doc="자본시장법", node=1,
        path="제166조의2", page=1, kind="법률좌표폐쇄", matched="exact-structural",
        text=OE_150, legal_meta={"validity": {"status": "current"}})
    monkeypatch.setattr(legalclosure_runtime, "retrieve", lambda *a, **k: (
        [section], {"strategy": "fixture", "selected": [
            {"doc_id": "o1", "node": 1, "origin": "exact-structural"}]}))

    out = compare.compare_article(None, idx, "n1", 1)
    assert len(out["후보"]) == 1
    assert out["후보"][0]["via"] == "간선" and out["후보"][0]["mandatory"]
    assert "exact-structural" in out["후보"][0]["origins"]
    assert out["후보"][0]["legal_meta"]["validity"]["status"] == "current"


def test_legalclosure_filters_internal_candidate_but_keeps_external_scope_companion(
        monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    idx._cross = ([], [])
    from lawrag.core.rag import legalclosure_runtime
    rows = [
        Section(n=1, doc_id="n2", doc="다른세칙", node=1, path="제1조", page=1,
                kind="법률좌표폐쇄", matched="noise", text="목적 조문"),
        Section(n=2, doc_id="o2", doc="금융투자업규정", node=2, path="제3-44조",
                page=2, kind="법률좌표폐쇄", matched="relation-closure",
                text="위험관리지침은 내부 보고 및 승인체계를 정하여야 한다",
                scope_out=True),
    ]
    monkeypatch.setattr(legalclosure_runtime, "retrieve", lambda *a, **k: (
        rows, {"strategy": "fixture", "selected": []}))

    out = compare.compare_article(None, idx, "n1", 1)
    assert [(row["doc_id"], row["scope_out"]) for row in out["후보"]] == [("o2", True)]


def test_unresolved_candidate_prevents_mixed_compliance_overclaim(monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    idx._cross = ([], [])
    from lawrag.core.rag import legalclosure_runtime
    rows = [
        Section(n=1, doc_id="o1", doc="자본시장법", node=1, path="제166조의2",
                page=1, kind="법률좌표폐쇄", matched="exact", text=OE_150),
        Section(n=2, doc_id="o2", doc="금융투자업규정", node=2, path="제3-44조",
                page=2, kind="법률좌표폐쇄", matched="assertion",
                text="위험관리지침은 내부 보고 및 승인체계를 정하여야 한다"),
    ]
    monkeypatch.setattr(legalclosure_runtime, "retrieve", lambda *a, **k: (
        rows, {"strategy": "fixture", "selected": []}))
    monkeypatch.setattr(compare, "compare_quants", lambda *a, **k: [])
    llm = _FakeLLM([
        {"n": 1, "판정": "부합", "근거": "부합", "인용": ""},
        {"n": 2, "판정": "불명", "근거": "본문만으로 불명", "인용": ""},
    ])

    out = compare.compare_article(llm, idx, "n1", 1)
    assert out["verdict"] == "재검토"
    assert out["완전성"]["미해결후보"] == [2]
    assert out["완전성"]["coverage_closed"] is False


def test_legalclosure_failure_is_visible_and_cannot_yield_compliance(monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    idx._cross = ([], [])
    from lawrag.core.rag import legalclosure_runtime

    def fail(*args, **kwargs):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(legalclosure_runtime, "retrieve", fail)
    out = compare.compare_article(None, idx, "n1", 1)
    assert out["verdict"] == "재검토" and out["짝없음"]
    assert out["검색"]["status"] == "degraded"
    assert "fixture failure" in out["검색"]["error"]


def test_promoted_atomic_compiler_keeps_deterministic_conflict(monkeypatch, tmp_path):
    idx = _mini(monkeypatch, tmp_path)
    from lawrag.core.rag import switches as switches_mod
    monkeypatch.setattr(
        switches_mod, "is_on",
        lambda key: key == "internal_compliance_compiler_v1")

    class CompilerLLM:
        def structured(self, kind, system, user, schema, **kwargs):
            assert kind == "rag.compare.atomic_compliance_compiler"
            return {
                "issues": [{"issue_id": "I1", "question_span": "필수 통제"}],
                "internal_units": [{
                    "claim_id": "N1", "evidence_id": "N:n1:1",
                    "issue_ids": ["I1"], "role": "GOVERNING_RULE",
                    "quote": "순자본비율이 100분의 120에 미달",
                }],
                "requirements": [{
                    "requirement_id": "R1", "evidence_id": "E:o1:1",
                    "issue_ids": ["I1"], "role": "GOVERNING_RULE",
                    "effect": "REQUIREMENT",
                    "quote": "순자본비율이 100분의 150에 미달",
                }],
                "bindings": [{
                    "requirement_id": "R1", "internal_claim_ids": ["N1"],
                    "status": "SATISFIED", "reason": "모델은 같다고 보았다",
                }],
                "reason": "fixture",
            }

    out = compare.compare_article(CompilerLLM(), idx, "n1", 1)
    assert out["verdict"] == "상충"
    assert out["컴파일"]["assessment"]["verdict"] == "부합"
    assert out["완전성"]["coverage_closed"] is False
    assert out["내규"]["evidence_id"] == "N:n1:1"
    assert out["후보"][0]["evidence_id"] == "E:o1:1"
