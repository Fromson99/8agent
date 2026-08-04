"""테스트 — 정규식 없는 파이프라인.

실행:  .venv/bin/python -m pytest trust_reconciler/tests -q

LLM 이 필요한 구간은 FakeClient(테스트 더블)로 대체한다.
프로덕션 코드에는 "LLM 흉내내는 휴리스틱"을 두지 않는다 —
가짜 판정이 리포트에 실려 사람을 속이면 안 되기 때문이다.
테스트 더블은 테스트 안에서만 살고, 미리 정한 답만 돌려준다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trust_reconciler import parsers, pipeline, report as reporting, textkit, units
from trust_reconciler.cache import SnapshotStore, prompt_fingerprint
from trust_reconciler.docmodel import (ElementValue, Provenance, TaggedDocument,
                                       TaggedElement, TaggedSection, to_jsonable)
from trust_reconciler.glossary import Glossary, Term
from trust_reconciler.llm.client import LLMUnavailable, SnapshotClient

ROOT = Path(__file__).parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).parents[1] / "config"
SCHEMA = json.loads((CONFIG / "tag_schema.json").read_text(encoding="utf-8"))
MAPPING = json.loads((CONFIG / "mapping_table.json").read_text(encoding="utf-8"))


# ===========================================================================
# 정규식 금지 — 회귀 방지
# ===========================================================================

def test_no_regex_in_production_code():
    """정규식은 dataset 실측에서 오버피팅이 확인되어 제거했다. 다시 들어오지 않게 막는다.

    근거(9종 전수조사): 금액 파서 오탐 80%(442건 중 356건),
    기준일 추출 성공률 44%, 6개 기준일 패턴 중 3개는 0회 매칭.
    """
    offenders = []
    for py in (ROOT / "trust_reconciler").rglob("*.py"):
        if "tests" in py.parts or "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        for i, line in enumerate(text.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped in ("import re", "import regex") or stripped.startswith("import re "):
                offenders.append(f"{py.relative_to(ROOT)}:{i} {stripped}")
            elif "re.compile(" in line or "re.search(" in line or "re.fullmatch(" in line:
                offenders.append(f"{py.relative_to(ROOT)}:{i} {stripped[:60]}")
    assert not offenders, "정규식이 다시 들어왔습니다:\n" + "\n".join(offenders)


# ===========================================================================
# textkit — regex 없는 문자열 처리
# ===========================================================================

def test_clean_unifies_punctuation_and_whitespace():
    assert textkit.clean("해지신탁원본  ×  요율   ÷ 365") == "해지신탁원본 * 요율 / 365"
    assert textkit.clean("‘신탁계약  세부내역서’") == "'신탁계약 세부내역서'"


def test_fold_ignores_spacing_and_case():
    assert textkit.fold("구 분") == textkit.fold("구분")
    assert textkit.fold("Notional") == textkit.fold("notional")
    assert textkit.fold("연 0.5%") == textkit.fold("연0.5%")


def test_fold_keeps_percent_sign():
    assert "%" in textkit.fold("연 0.5%")


@pytest.mark.parametrize("raw", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    '설명 문장입니다.\n{"a": 1}\n끝.',
    '{"s": "중괄호 } 가 문자열 안에 있음", "a": 1}',
])
def test_extract_json_survives_wrappers(raw):
    """LLM 응답 정리 — 코드펜스·앞뒤 문장·문자열 속 괄호를 견딘다. 괄호 세기로 구현했다."""
    got = textkit.extract_json(raw)
    assert got["a"] == 1


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError):
        textkit.extract_json("JSON 이 전혀 없는 응답")


# ===========================================================================
# units — 구조화된 값 비교 (2단계의 핵심)
# ===========================================================================

def test_duration_years_equals_months():
    v, why = units.compare("duration", {"years": 3}, {"months": 36})
    assert v == "match" and "36" in why


def test_duration_mismatch_is_definite():
    assert units.compare("duration", {"years": 3}, {"years": 2})[0] == "mismatch"


def test_percent_same_value_different_annualization_is_uncertain():
    """0.5% 와 연 0.5% 는 숫자가 같아도 실질이 다를 수 있다. 확정하지 않는다."""
    v, _ = units.compare("percent", {"value": 0.5, "per_annum": True},
                         {"value": 0.5, "per_annum": False})
    assert v == "uncertain"


def test_percent_match_and_mismatch():
    assert units.compare("percent", {"value": 0.5, "per_annum": True},
                         {"value": 0.5, "per_annum": True})[0] == "match"
    assert units.compare("percent", {"value": 0.5, "per_annum": True},
                         {"value": 0.7, "per_annum": True})[0] == "mismatch"


def test_money_compares_amount_not_text():
    """예전 정규식 파서는 '「소득세법」 제14조'의 '조'를 4조원으로 읽었다(오탐 80%).
    이제 LLM 이 준 정수만 비교하므로 그런 오탐이 구조적으로 불가능하다."""
    assert units.compare("money", {"amount": 100_000_000, "currency": "KRW"},
                         {"amount": 100_000_000})[0] == "match"
    assert units.compare("money", {"amount": 100_000_000}, {"amount": 90_000_000})[0] == "mismatch"


def test_money_currency_mismatch():
    assert units.compare("money", {"amount": 100, "currency": "KRW"},
                         {"amount": 100, "currency": "USD"})[0] == "mismatch"


def test_enum_uses_mapping_table():
    """위험등급 표기 체계가 달라도 매핑표로 통일된다."""
    v, why = units.compare("enum", {"raw": "2등급"}, {"raw": "높은위험"}, MAPPING["risk_grade"])
    assert v == "match" and "G2" in why


def test_enum_longest_surface_wins():
    v, _ = units.compare("enum", {"raw": "1등급"}, {"raw": "매우높은위험"}, MAPPING["risk_grade"])
    assert v == "match"
    v, _ = units.compare("enum", {"raw": "2등급"}, {"raw": "매우높은위험"}, MAPPING["risk_grade"])
    assert v == "mismatch"


def test_enum_unknown_surface_is_uncertain():
    v, _ = units.compare("enum", {"raw": "초위험군"}, {"raw": "2등급"}, MAPPING["risk_grade"])
    assert v == "uncertain"


def test_formula_compares_operand_multiset():
    a = {"operands": ["해지신탁원본", "중도해지수수료율", "경과일수", "365"], "ops": ["*", "*", "/"]}
    b = {"operands": ["경과일수", "365", "해지신탁원본", "중도해지수수료율"], "ops": ["/", "*", "*"]}
    assert units.compare("formula", a, b)[0] == "match"


def test_formula_missing_operand_is_mismatch():
    a = {"operands": ["해지신탁원본", "요율", "경과일수", "365"], "ops": ["*", "*", "/"]}
    b = {"operands": ["해지신탁원본", "요율"], "ops": ["*"]}
    v, why = units.compare("formula", a, b)
    assert v == "mismatch" and "365" in why


def test_boolean_and_date():
    assert units.compare("boolean", {"value": False}, {"value": False})[0] == "match"
    assert units.compare("boolean", {"value": True}, {"value": False})[0] == "mismatch"
    assert units.compare("date", {"iso": "2024-06-03"}, {"iso": "2024-06-03"})[0] == "match"


def test_ref_is_never_confirmed():
    """양쪽 다 '별지1 참조'면 값을 비교한 것이 아니다. 확정하면 안 된다."""
    assert units.compare("ref", {"target": "별지1"}, {"target": "별지1"})[0] == "uncertain"


def test_text_needs_llm():
    v, _ = units.compare("text", {"text": "원금 손실 가능"}, {"text": "원본 손실이 발생할 수 있음"})
    assert v == "uncertain"
    assert units.needs_llm(v, "text")


def test_unknown_value_type_is_uncertain_not_crash():
    assert units.compare("무슨타입", {}, {})[0] == "uncertain"


# ===========================================================================
# glossary — 사용자 추가 + LLM 추천
# ===========================================================================

@pytest.fixture
def glossary():
    return Glossary.load(CONFIG / "glossary.json")


def test_glossary_lookup_and_find(glossary):
    assert glossary.lookup("기본보수") == "trust_fee"
    assert glossary.lookup("해지원본") == "terminated_principal"
    found = glossary.find_in("중도해지수수료는 해지신탁원본 × 중도해지수수료율 × 경과일수 ÷ 365")
    assert "early_termination_fee" in found and "terminated_principal" in found


def test_glossary_separates_fee_from_rate(glossary):
    """수수료(결과 금액)와 수수료율(피연산자)은 다른 용어여야 한다.

    실측 근거: 한 용어로 묶었더니 계약서의 '중도해지수수료율'이 canonical display
    '중도해지수수료'로 정규화되고 설명서 쪽은 '중도해지수수료율'로 남아,
    같은 산식이 "구성 요소가 다름"으로 잘못 판정됐다.
    """
    assert glossary.lookup("신탁보수율") == "trust_fee_rate"
    assert glossary.lookup("신탁보수") == "trust_fee"
    assert glossary.lookup("중도해지수수료율") == "early_termination_fee_rate"
    assert glossary.lookup("중도해지수수료") == "early_termination_fee"


def test_glossary_absorbs_llm_suggestions(glossary):
    applied = glossary.absorb([
        {"canonical": "trust_fee", "surfaces": ["운용관리보수"], "value_type": "percent"},
        {"canonical": "custody_fee", "display": "보관수수료", "surfaces": ["보관수수료"],
         "value_type": "percent"},
    ])
    kinds = {a["kind"] for a in applied}
    assert kinds == {"surface_added", "new_term"}
    assert glossary.lookup("운용관리보수") == "trust_fee"
    assert glossary.lookup("보관수수료") == "custody_fee"
    assert any(p["canonical"] == "custody_fee" for p in glossary.pending_review())


def test_glossary_never_overwrites_user_terms():
    g = Glossary([Term(canonical="trust_fee", display="신탁보수",
                       surfaces=["신탁보수"], source="user")])
    g.absorb([{"canonical": "trust_fee", "surfaces": ["엉뚱한표현"]}])
    assert g.lookup("엉뚱한표현") is None


def test_glossary_confusable(glossary):
    assert "early_termination_fee" in glossary.confusable("trust_fee")


# ===========================================================================
# P1 파싱 — 도클링 + 보완
# ===========================================================================

def test_parse_text_fixture_produces_blocks_and_tables():
    doc = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    assert doc.blocks
    assert doc.stats["tables"] >= 2          # 별지1·별표2
    assert any(b.kind == "section_header" for b in doc.blocks)
    assert all(b.provenance is not None for b in doc.blocks)


def test_parse_docx_reads_style_headings():
    docx = FIXTURES / "case_e_docx" / "contract.docx"
    if not docx.exists():
        pytest.skip("DOCX 픽스처 없음")
    doc = parsers.parse(str(docx), "contract")
    heads = [b.text for b in doc.blocks if b.kind == "section_header"]
    assert "제11조 (신탁기본보수)" in heads and "제16조 (중도해지)" in heads


def test_parse_rejects_unknown_format(tmp_path):
    p = tmp_path / "x.hwp"
    p.write_text("dummy", encoding="utf-8")
    with pytest.raises(ValueError):
        parsers.parse(str(p), "contract")


def test_parse_rejects_bad_role():
    with pytest.raises(ValueError):
        parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "무엇인가")


def test_parse_content_hash_is_stable():
    a = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    b = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    assert a.content_hash == b.content_hash and a.doc_id == b.doc_id


@pytest.mark.slow
def test_parse_real_pdf_with_docling():
    pdf = ROOT / "dataset" / "유안타 증권 특정금전신탁 계약서(일반형).pdf"
    if not pdf.exists():
        pytest.skip("dataset PDF 없음")
    doc = parsers.parse(str(pdf), "contract")
    assert doc.parser.startswith("docling")
    assert len(doc.blocks) > 100
    # 도클링이 이 문서의 표를 놓쳐 pdfplumber 가 보완한다 — 실측으로 확인된 동작
    assert doc.stats["tables"] > 0
    assert doc.stats["dropped_header_footer"] > 0      # 머리말/꼬리말 제거


# ===========================================================================
# 스냅샷 — 재현성 확보
# ===========================================================================

def test_snapshot_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path / "s.json", prompt_fingerprint="fp1")
    payload = {"doc_role": "contract", "blocks": [{"block_id": "b1"}]}
    assert store.get("tag_blocks", payload) is None
    store.put("tag_blocks", payload, {"assignments": [{"block_id": "b1", "tag": "trust_fee"}]})
    assert store.save()
    again = SnapshotStore(tmp_path / "s.json", prompt_fingerprint="fp1")
    assert again.get("tag_blocks", payload)["assignments"][0]["tag"] == "trust_fee"


def test_snapshot_invalidated_when_prompt_changes(tmp_path):
    """프롬프트를 고치면 낡은 판정이 남으면 안 된다."""
    payload = {"x": 1}
    s1 = SnapshotStore(tmp_path / "s.json", prompt_fingerprint="fp1")
    s1.put("doc_meta", payload, {"issuer": "A"})
    s1.save()
    s2 = SnapshotStore(tmp_path / "s.json", prompt_fingerprint="fp2")
    assert s2.get("doc_meta", payload) is None


def test_prompt_fingerprint_is_stable():
    assert prompt_fingerprint() == prompt_fingerprint()


def test_snapshot_client_refuses_to_invent(tmp_path):
    """스냅샷에 없으면 조용히 빈 결과를 내지 않고 실패한다. 가짜 판정 금지."""
    client = SnapshotClient(SnapshotStore(tmp_path / "s.json"))
    with pytest.raises(LLMUnavailable):
        client.tag_blocks({"doc_role": "contract", "blocks": []})


# ===========================================================================
# 테스트 더블 — 미리 정한 답만 돌려준다
# ===========================================================================

class FakeClient:
    name = "fake"

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[str] = []

    def call(self, kind, payload):
        self.calls.append(kind)
        r = self.responses.get(kind)
        return r(payload) if callable(r) else (r or {})

    def tag_blocks(self, p): return self.call("tag_blocks", p)
    def extract_elements(self, p): return self.call("extract_elements", p)
    def pair_sections(self, p): return self.call("pair_sections", p)
    def compare_values(self, p): return self.call("compare_values", p)
    def doc_meta(self, p): return self.call("doc_meta", p)


def _tagged(doc_role, entries) -> TaggedDocument:
    """(tag, {element_id: (value_type, raw, data)}) 목록으로 TaggedDocument 를 만든다."""
    td = TaggedDocument(doc_id=f"d_{doc_role}", doc_role=doc_role, backend="fake")
    for i, (tag, elements, terms) in enumerate(entries):
        sec = TaggedSection(section_id=f"{doc_role}_s{i:03d}", tag=tag, title=tag,
                            tag_confidence=0.95, terms=terms,
                            provenance=Provenance(page=1))
        for eid, (vt, raw, data) in elements.items():
            sec.elements.append(TaggedElement(
                element_id=eid, display=eid, confidence=0.9,
                value=ElementValue(value_type=vt, raw=raw, data=data)))
        td.sections.append(sec)
    return td


# ===========================================================================
# P2 태깅 — 연속 블록 묶기
# ===========================================================================

def test_tagging_groups_consecutive_blocks_into_sections():
    doc = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    ids = [b.block_id for b in doc.blocks]
    llm = FakeClient({
        "tag_blocks": {"assignments": [
            {"block_id": ids[0], "tag": "trust_fee", "confidence": 0.9, "title": "제11조"},
            {"block_id": ids[1], "tag": "trust_fee", "confidence": 0.8},
            {"block_id": ids[2], "tag": "trust_period", "confidence": 0.9},
        ]},
        "extract_elements": {"elements": []},
    })
    td = pipeline.tag_document(doc, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    tags = [s.tag for s in td.sections]
    assert tags == ["trust_fee", "trust_period"]        # 연속 두 블록이 한 섹션으로
    assert len(td.sections[0].block_ids) == 2
    assert td.sections[0].tag_confidence == 0.9         # 구간 내 최댓값


def test_tagging_does_not_merge_separated_same_tag():
    """앞뒤로 떨어진 같은 태그는 합치지 않는다 — 출처를 잃으면 안 된다.
    (제11조의 보수율과 별지1의 보수율은 따로 두고, 1:N 대응은 P3 가 처리한다)"""
    doc = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    ids = [b.block_id for b in doc.blocks]
    llm = FakeClient({
        "tag_blocks": {"assignments": [
            {"block_id": ids[0], "tag": "trust_fee", "confidence": 0.9},
            {"block_id": ids[1], "tag": "trust_period", "confidence": 0.9},
            {"block_id": ids[2], "tag": "trust_fee", "confidence": 0.9},
        ]},
        "extract_elements": {"elements": []},
    })
    td = pipeline.tag_document(doc, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    assert [s.tag for s in td.sections] == ["trust_fee", "trust_period", "trust_fee"]


def test_tagging_collects_schema_and_glossary_suggestions():
    doc = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    g = Glossary.load(CONFIG / "glossary.json")
    llm = FakeClient({
        "tag_blocks": {"assignments": [],
                       "suggestions": [{"proposed_id": "notification_cycle",
                                        "display": "운용내역 통보 주기", "why": "양쪽에 있음"}],
                       "glossary_suggestions": [{"canonical": "custody_fee",
                                                 "display": "보관수수료",
                                                 "surfaces": ["보관수수료"]}]},
        "extract_elements": {"elements": []},
    })
    td = pipeline.tag_document(doc, SCHEMA, g, llm)
    assert any(s.get("proposed_id") == "notification_cycle" for s in td.suggestions)
    assert g.lookup("보관수수료") == "custody_fee"


# ===========================================================================
# P3 1단계 — 섹션 대응
# ===========================================================================

def test_pairing_matches_same_tag_without_llm():
    c = _tagged("contract", [("trust_fee", {}, ["trust_fee"])])
    s = _tagged("statement", [("trust_fee", {}, ["trust_fee"])])
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    ok = [p for p in pairs if p.flag == "ok"]
    assert len(ok) == 1 and ok[0].method == "tag"
    assert "pair_sections" not in llm.calls        # 확신도 높은 동일 태그는 LLM 을 안 부른다


def test_pairing_reports_unpaired_sections():
    c = _tagged("contract", [("trust_fee", {}, ["trust_fee"]),
                             ("beneficiary", {}, ["beneficiary"])])
    s = _tagged("statement", [("trust_fee", {}, ["trust_fee"])])
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    lonely = [p for p in pairs if p.flag == "contract_only"]
    assert len(lonely) == 1 and lonely[0].tag == "beneficiary"


def test_pairing_skips_statement_only_tags():
    """설명서 단독 항목(연계·제휴 등)은 계약서에 없는 것이 정상 — 대사 쌍을 만들지 않는다."""
    c = _tagged("contract", [])
    s = _tagged("statement", [("affiliated_service", {}, [])])
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    assert not [p for p in pairs if p.tag == "affiliated_service"]


def test_pairing_candidate_reduction_avoids_full_cross_product():
    """섹션이 많아도 공유 용어가 없으면 후보에서 빠진다 (비용 통제)."""
    c = _tagged("contract", [(f"trust_fee", {}, ["trust_fee"]),
                             ("beneficiary", {}, ["beneficiary"])])
    s = _tagged("statement", [("trust_fee", {}, ["trust_fee"]),
                              ("tax_treatment", {}, ["tax_treatment"])])
    cands = pipeline._candidates(c, s)
    assert len(cands) == 1                        # 2x2=4 중 1쌍만 후보


def test_pairing_low_confidence_is_flagged_uncertain():
    c = _tagged("contract", [("trust_fee", {}, ["trust_fee"])])
    s = _tagged("statement", [("front_end_fee", {}, ["trust_fee"])])
    llm = FakeClient({"pair_sections": {"pairs": [{
        "candidate_id": "c000", "same": True, "confidence": 0.4,
        "contract_section_ids": ["contract_s000"], "statement_section_ids": ["statement_s000"],
        "evidence": "애매함"}]}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    assert any(p.flag == "uncertain" for p in pairs)


# ===========================================================================
# P4 2단계 — 값 비교
# ===========================================================================

def _fee_docs(c_rate, s_rate):
    c = _tagged("contract", [("trust_fee",
                              {"rate": ("percent", f"연 {c_rate}%",
                                        {"value": c_rate, "per_annum": True})},
                              ["trust_fee"])])
    s = _tagged("statement", [("trust_fee",
                               {"rate": ("percent", f"{s_rate}%(연율)",
                                         {"value": s_rate, "per_annum": True})},
                               ["trust_fee"])])
    return c, s


def test_comparison_detects_value_mismatch():
    c, s = _fee_docs(0.5, 0.7)
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    out = pipeline.compare_elements(pairs, c, s, SCHEMA, MAPPING, llm)
    rate = next(x for x in out if x.element_id == "rate")
    assert rate.verdict == "mismatch" and rate.is_key
    assert "0.5" in rate.reason and "0.7" in rate.reason


def test_comparison_matches_equivalent_values():
    c, s = _fee_docs(0.5, 0.5)
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    out = pipeline.compare_elements(pairs, c, s, SCHEMA, MAPPING, llm)
    assert next(x for x in out if x.element_id == "rate").verdict == "match"
    assert "compare_values" not in llm.calls        # 코드가 판정했으면 LLM 을 안 부른다


def test_comparison_falls_back_to_llm_for_text():
    c = _tagged("contract", [("invest_method",
                              {"method": ("text", "만기보유 원칙", {"text": "만기까지 보유"})}, [])])
    s = _tagged("statement", [("invest_method",
                               {"method": ("text", "만기까지 보유", {"text": "만기보유가 원칙"})}, [])])
    llm = FakeClient({"pair_sections": {"pairs": []},
                      "compare_values": {"verdict": "match", "reason": "같은 뜻", "confidence": 0.9}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    out = pipeline.compare_elements(pairs, c, s, SCHEMA, MAPPING, llm)
    m = next(x for x in out if x.element_id == "method")
    assert m.verdict == "match" and m.method == "llm_semantic"


def test_uncertain_pair_downgrades_mismatch():
    """섹션 대응이 불확실하면 값 불일치를 확정하지 않는다.
    잘못 짝지은 두 섹션을 비교하면 반드시 불일치가 나오기 때문이다."""
    c, s = _fee_docs(0.5, 0.7)
    llm = FakeClient({"pair_sections": {"pairs": [{
        "candidate_id": "c000", "same": True, "confidence": 0.3,
        "contract_section_ids": ["contract_s000"], "statement_section_ids": ["statement_s000"],
        "evidence": "애매"}]}})
    c.sections[0].tag_confidence = 0.5             # 확신도를 낮춰 LLM 경로를 타게 한다
    s.sections[0].tag_confidence = 0.5
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    out = pipeline.compare_elements(pairs, c, s, SCHEMA, MAPPING, llm)
    rate = next(x for x in out if x.element_id == "rate")
    assert rate.verdict == "uncertain" and "불확실" in rate.reason


def test_missing_key_element_is_reported():
    c = _tagged("contract", [("trust_fee",
                              {"rate": ("percent", "연 0.5%", {"value": 0.5, "per_annum": True})},
                              ["trust_fee"])])
    s = _tagged("statement", [("trust_fee", {}, ["trust_fee"])])
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    out = pipeline.compare_elements(pairs, c, s, SCHEMA, MAPPING, llm)
    assert any(x.verdict == "missing_side" and x.element_id == "rate" for x in out)


# ===========================================================================
# 완결성 + 리포트
# ===========================================================================

def test_completeness_conditional_requirement():
    """케이스 9 — 단순 채권형에 조기상환 조건이 없는 것은 오류가 아니다."""
    s = _tagged("statement", [("trust_fee", {}, [])])
    normal = {r.tag: r for r in reporting.check_completeness(s, SCHEMA, "일반")}
    els = {r.tag: r for r in reporting.check_completeness(s, SCHEMA, "ELS편입")}
    assert normal["redemption_terms"].verdict == "not_applicable"
    assert els["redemption_terms"].verdict == "missing"


def test_completeness_marks_missing_required():
    s = _tagged("statement", [("trust_fee", {}, [])])
    res = {r.tag: r for r in reporting.check_completeness(s, SCHEMA, "일반")}
    assert res["withdrawal_right"].verdict == "missing"
    assert res["trust_fee"].verdict == "ok"


def _mini_report(product_type="ELS편입"):
    c_parsed = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    s_parsed = parsers.parse(str(FIXTURES / "case_a" / "statement.txt"), "product_statement")
    c_parsed.meta.version_date, s_parsed.meta.version_date = "2024-03-01", "2021-09-01"
    c_parsed.meta.issuer, s_parsed.meta.issuer = "A증권", "B은행"
    c_parsed.meta.product_type = s_parsed.meta.product_type = product_type
    c, s = _fee_docs(0.5, 0.7)
    llm = FakeClient({"pair_sections": {"pairs": []}})
    pairs = pipeline.pair_sections(c, s, SCHEMA, Glossary.load(CONFIG / "glossary.json"), llm)
    comps = pipeline.compare_elements(pairs, c, s, SCHEMA, MAPPING, llm)
    comp = reporting.check_completeness(s, SCHEMA, product_type)
    return reporting.build(c_parsed, s_parsed, c, s, pairs, comps, comp, SCHEMA,
                           backend="fake")


def test_report_warns_on_version_gap_and_issuer_mismatch():
    rep = _mini_report()
    assert any("기준일 차이" in w for w in rep.warnings)
    assert any("발행사가 다름" in w for w in rep.warnings)


def test_report_ranks_key_mismatch_as_high():
    rep = _mini_report()
    top = rep.findings[0]
    assert top.severity == "high" and top.type == "mismatch"
    assert rep.summary["mismatch"] == 1


def test_report_markdown_and_json():
    rep = _mini_report()
    md = reporting.to_markdown(rep)
    assert "# 신탁계약서 ↔ 핵심상품설명서 대사 리포트" in md
    assert "1단계" in md and "2단계 상세" in md and "완결성 상세" in md
    assert json.dumps(to_jsonable(rep), ensure_ascii=False)


def test_report_shows_schema_suggestions():
    c, s = _fee_docs(0.5, 0.5)
    c.suggestions.append({"proposed_id": "notification_cycle", "display": "운용내역 통보 주기",
                          "why": "양쪽에 있으나 스키마에 없음", "doc_role": "contract"})
    c_parsed = parsers.parse(str(FIXTURES / "case_a" / "contract.txt"), "contract")
    s_parsed = parsers.parse(str(FIXTURES / "case_a" / "statement.txt"), "product_statement")
    rep = reporting.build(c_parsed, s_parsed, c, s, [], [], [], SCHEMA, backend="fake")
    assert rep.summary["schema_suggestions"] == 1
    assert "스키마 추가 제안" in reporting.to_markdown(rep)


# ===========================================================================
# 사용자 선언 스키마
# ===========================================================================

def test_schema_declares_two_tiers():
    """메인 요소(섹션)와 세부 요소(elements)의 2계층이 선언되어 있어야 한다."""
    assert SCHEMA["sections"]
    for s in SCHEMA["sections"]:
        assert s["id"] and s["display"]
        for e in s.get("elements", []):
            assert e["value_type"] in SCHEMA["value_types"], f"{s['id']}.{e['id']}"


def test_schema_can_be_narrowed_by_user_selection():
    from trust_reconciler.main import filter_schema
    narrowed = filter_schema(SCHEMA, ["trust_fee", "trust_period"])
    assert {s["id"] for s in narrowed["sections"]} == {"trust_fee", "trust_period"}


def test_every_key_element_has_display():
    for s in SCHEMA["sections"]:
        for e in s.get("elements", []):
            assert e.get("display"), f"{s['id']}.{e['id']} 에 display 가 없습니다"
