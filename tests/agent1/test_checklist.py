"""검사 항목 파이프라인 — 용어로 범위를 찾고, 출처 위조가 막히는지 시험한다.

docling·LLM 없이 돈다. 구조화는 합성 Document 로 건너뛰고(그 검증은
test_golden), LLM 은 스텁으로 갈아 끼운다 — 여기서 시험하는 것은 **찾기가
결정론인가**와 **증거 ID 계약이 검사 모드에서도 지켜지는가**다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents" / "agent1" / "src"))

import checklist                                           # noqa: E402
from core.structurize import Document, Section             # noqa: E402


# ---------------------------------------------------------------- 재료
def _contract() -> Document:
    return Document(doc_type="특정금전신탁", format_version=1,
                    source_file="contract.pdf", sections=[
        Section(section_id="제1조/신탁기간", marker={}, path=["제1조", "신탁기간"],
                level=2, content=[{"type": "text", "page": 2,
                                   "text": "신탁기간은 2024-06-03 부터 2025-06-03 까지로 한다."}]),
        Section(section_id="제2조/신탁보수", marker={}, path=["제2조", "신탁보수"],
                level=2, content=[{"type": "text", "page": 2,
                                   "text": "기본보수는 연 1.0% 로 한다."}]),
        Section(section_id="제3조/일반사항", marker={}, path=["제3조", "일반사항"],
                level=2, content=[{"type": "text", "page": 3,
                                   "text": "중도해지수수료는 해지금액의 0.5% 로 한다."}]),
    ])


def _prospectus() -> Document:
    return Document(doc_type="투자설명서", format_version=1,
                    source_file="prospectus.pdf", sections=[
        Section(section_id="제2부/신탁기간", marker={}, path=["제2부", "신탁기간"],
                level=2, content=[{"type": "text", "page": 11,
                                   "text": "이 투자신탁의 신탁기간은 2024-06-03 부터 2026-06-03 까지이다."}]),
        Section(section_id="제2부/보수", marker={}, path=["제2부", "보수 및 수수료"],
                level=2, content=[{"type": "text", "page": 13,
                                   "text": "중도해지수수료: 없음"}]),
    ])


class StubLLM:
    """정해 둔 응답을 차례로 내놓는다 — 판정 로직이 아니라 계약을 시험한다."""
    model = "stub"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def structured(self, kind, system, user, schema, **kw):
        self.calls.append({"kind": kind, "user": user})
        return self.replies.pop(0) if self.replies else None

    def totals(self):
        return {"calls": len(self.calls)}


# ---------------------------------------------------------------- 찾기 (결정론)
def test_제목에_있으면_그_구역이다():
    f = checklist.find_sections(_contract(), "신탁기간")
    assert f.how == "제목"
    assert f.section_ids == ["제1조/신탁기간"]


def test_제목에_없으면_본문으로_내려간다():
    f = checklist.find_sections(_contract(), "중도해지수수료")
    assert f.how == "본문"
    assert f.section_ids == ["제3조/일반사항"]


def test_어디에도_없으면_없음():
    f = checklist.find_sections(_contract(), "존재하지않는용어")
    assert f.how == "없음" and f.section_ids == []


def test_별칭으로도_찾는다():
    f = checklist.find_sections(_contract(), "환매수수료",
                                aliases=["중도해지수수료"])
    assert f.how == "본문" and f.section_ids == ["제3조/일반사항"]


def test_찾은_구역이_증거_표가_된다():
    sc, found = checklist.term_scope(_contract(), "계약서", "신탁기간")
    assert found.how == "제목"
    assert len(sc.evidence) == 1
    assert "2025-06-03" in sc.evidence[0].text
    assert sc.evidence[0].section_id == "제1조/신탁기간"


# ---------------------------------------------------------------- 검사 실행
def test_값이_다르면_그렇게_보고된다():
    llm = StubLLM([{
        "term": "신탁기간",
        "source_value": "2024-06-03 ~ 2025-06-03", "source_evidence": ["e-001"],
        "target_value": "2024-06-03 ~ 2026-06-03", "target_evidence": ["e-001"],
        "verdict": "VALUE_MISMATCH", "reason": "만료일이 다르다", "candidates": [],
    }])
    report = checklist.check_docs(_contract(), _prospectus(),
                                  [{"id": "c-period", "term": "신탁기간"}], llm)
    row = report.rows[0]
    assert row.verdict == "VALUE_MISMATCH"
    assert row.method == "checklist"
    # 증거 ID 가 실제 출처로 되돌아왔다 — 페이지·구역 좌표가 붙는다
    assert row.source_refs[0]["section_id"] == "제1조/신탁기간"
    assert row.source_refs[0]["page"] == 2
    assert row.target_refs[0]["section_id"] == "제2부/신탁기간"
    assert report.stats["틀림"] == 1


def test_지어낸_증거_ID는_판정을_무효로_만든다():
    llm = StubLLM([{
        "term": "신탁기간",
        "source_value": "2024-06-03", "source_evidence": ["e-999"],   # 없는 ID
        "target_value": "2024-06-03", "target_evidence": ["e-001"],
        "verdict": "MATCH", "reason": "같다", "candidates": [],
    }])
    report = checklist.check_docs(_contract(), _prospectus(),
                                  [{"id": "c-period", "term": "신탁기간"}], llm)
    row = report.rows[0]
    assert row.verdict == "NEEDS_REVIEW"                 # 확정 판정이 내려가지 않는다
    assert any("지어낸 근거" in w for w in row.warnings)


def test_정답에_용어가_없으면_LLM을_부르지_않는다():
    llm = StubLLM([])
    report = checklist.check_docs(_contract(), _prospectus(),
                                  [{"id": "c-x", "term": "존재하지않는용어"}], llm)
    row = report.rows[0]
    assert row.verdict == "SOURCE_EXTRACTION_FAILED"
    assert row.method == "search"
    assert llm.calls == []                               # 판정을 부를 것이 없었다


def test_발견_기록이_리포트에_남는다():
    llm = StubLLM([{
        "term": "중도해지수수료",
        "source_value": "0.5%", "source_evidence": ["e-001"],
        "target_value": "없음", "target_evidence": ["e-001"],
        "verdict": "VALUE_MISMATCH", "reason": "다르다", "candidates": [],
    }])
    report = checklist.check_docs(_contract(), _prospectus(),
                                  [{"id": "c-redeem", "term": "중도해지수수료"}], llm)
    found = report.scopes["c-redeem"]["found"]
    assert found["contract"]["how"] == "본문"            # 계약서는 본문에서
    assert found["prospectus"]["how"] == "본문"          # 설명서도 본문에서
    assert report.scopes["c-redeem"]["contract"]["evidence"]


def test_기본_검사_항목_파일이_읽힌다():
    checks = checklist.load_checks()
    assert checks and all(c.get("term") for c in checks)


# ---------------------------------------------------------------- 탐색(사다리) 폴백
def _doc_ladder() -> Document:
    """정확 매칭이 빗나가는 재료 — 사다리가 잡아야 하는 두 경우."""
    return Document(doc_type="특정금전신탁", format_version=1,
                    source_file="ladder.pdf", sections=[
        Section(section_id="제4조/중도해지수수료", marker={},
                path=["제4조", "중도해지수수료"], level=2,
                content=[{"type": "text", "page": 4,
                          "text": "해지 시 수수료는 0.5% 로 한다."}]),
        Section(section_id="제5조/기타", marker={}, path=["제5조", "기타"], level=2,
                content=[{"type": "text", "page": 5,
                          "text": "청약철회권 행사 기간은 7일로 한다."}]),
    ])


def test_어댑터_좌표_대응표():
    meta, result, sec_of = __import__("core.rag.adapt", fromlist=["view_of"]).view_of(_contract())
    assert meta["name"] == "contract.pdf"
    assert len(result["nodes"]) == 3 and len(result["blocks"]) == 3
    assert sec_of[1] == "제1조/신탁기간"
    assert result["nodes"][0]["span"] == [0, 1]        # 구역 하나 = 블록 범위 하나


def test_사다리_제목이_질의에_들어_있으면_잡는다():
    # `중도해지수수료율` — 표면형⊂문서 는 빗나가지만(율 때문에),
    # 사다리의 반대 방향(제목⊂질의)이 잡는다.
    f = checklist.find_sections(_doc_ladder(), "중도해지수수료율")
    assert f.how == "탐색"
    assert f.section_ids == ["제4조/중도해지수수료"]
    assert f.trail                                     # 왜 이 구역인지가 남는다


def test_사다리_조사_붙은_말은_접두_확장이_잡는다():
    # `청약철회권을` — 본문의 `청약철회권` 과 정확히는 다르지만 접두 관계다.
    f = checklist.find_sections(_doc_ladder(), "청약철회권을")
    assert f.how == "탐색"
    assert f.section_ids == ["제5조/기타"]


def test_탐색으로_찾은_범위는_판정에_경고가_남는다():
    llm = StubLLM([{
        "term": "중도해지수수료율",
        "source_value": "0.5%", "source_evidence": ["e-001"],
        "target_value": "0.5%", "target_evidence": ["e-001"],
        "verdict": "MATCH", "reason": "같다", "candidates": [],
    }])
    report = checklist.check_docs(_doc_ladder(), _doc_ladder(),
                                  [{"id": "c-x", "term": "중도해지수수료율"}], llm)
    row = report.rows[0]
    assert row.verdict == "MATCH"                      # 값 판정 자체는 유효하고
    assert any("유사 검색" in w for w in row.warnings)   # 범위의 근거가 약함이 남는다
