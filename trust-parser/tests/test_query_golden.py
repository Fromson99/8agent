"""T24. 검색 골든 — 결정론 라우터 (SPEC §D3).

**임베딩이 없다.** 매 단계가 재현 가능해야 하며, 같은 질의는 같은 청크를 낸다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import chunk_search          # noqa: E402
import fact_query            # noqa: E402
import ontology              # noqa: E402
import query_router          # noqa: E402
from schema import ChunkDocument   # noqa: E402

PAIR = ROOT / "data" / "golden_pairs" / "acct_001"


@pytest.fixture(scope="module")
def onto():
    return ontology.load(ontology.default_path(ROOT))


@pytest.fixture(scope="module")
def doc():
    raw = json.loads((PAIR / "contract.chunks.json").read_text(encoding="utf-8"))
    return ChunkDocument.model_validate(raw)


@pytest.fixture(scope="module")
def store(doc, onto):
    return fact_query.FactStore(doc, onto)


# ===========================================================================
# T21 — 질의 분류 (LLM 없이 규칙만으로)
# ===========================================================================

@pytest.mark.parametrize("q,field,intent", [
    ("신탁금액이 얼마인가요?",        "신탁금액", "value"),
    ("투자금액 얼마야",               "신탁금액", "value"),      # alias 치환
    ("계약기간이 언제까지지?",        "신탁기간", "value"),
    ("성과보수 몇 퍼센트야",          "수익보수", "value"),
    ("계좌번호 뭐야",                 "계좌번호", "value"),
])
def test_value_queries_route_to_fact(q, field, intent, onto):
    r = query_router.classify(q, onto)          # llm=None — 규칙만
    assert r.intent == intent
    assert r.field == field, f"{q} → {r.field} (경로 {r.path})"
    assert r.role == onto.fields[field].source_of_truth
    assert "alias:" in " ".join(r.path), "alias 치환 경로가 기록되지 않았습니다"


@pytest.mark.parametrize("q", [
    "중도해지는 어떻게 하나요?",
    "신탁재산을 운용하는 절차가 뭐야",
])
def test_explain_queries_are_not_value(q, onto):
    r = query_router.classify(q, onto)
    assert r.intent == "explain"


def test_classification_is_deterministic(onto):
    a = query_router.classify("신탁금액이 얼마인가요?", onto)
    b = query_router.classify("신탁금액이 얼마인가요?", onto)
    assert (a.intent, a.field, a.role, a.path) == (b.intent, b.field, b.role, b.path)


# ===========================================================================
# T22 — fact 직조회 (§D3-1: 값 질문은 fact 로 답한다)
# ===========================================================================

def test_value_question_answered_from_fact(store):
    a = store.get("신탁금액")
    assert a.found and a.value == 100_000_000
    assert a.raw and a.source, "인용 근거(raw·source)가 비었습니다"


def test_derived_field_is_computed_not_searched(store):
    """만기일은 별지1에 없다 — 신탁기간.end 로 계산돼야 한다."""
    a = store.get("만기일")
    assert a.found and a.derived_from == "신탁기간.end"
    assert str(a.value) == "2027-06-02", a.value


def test_unknown_field_fails_loudly(store):
    a = store.get("없는필드")
    assert not a.found and "fact_store:unknown_field" in a.route


# ===========================================================================
# T23 — 청크 검색 (§D3-2: facet 필터 → 렉시컬 → refs 확장 → small-to-big)
# ===========================================================================

def test_facet_filter_narrows_before_search(doc, onto):
    body = chunk_search.facet_filter(doc, role=onto.default_role())
    app = chunk_search.facet_filter(doc, role="별지1_입력")
    assert body and app and not (body & app), "role 필터가 겹칩니다"


def test_lexical_search_is_ranked_and_explainable(doc):
    idx = chunk_search.ChunkIndex(doc)
    hits = idx.search(["중도해지", "수수료"], top=3)
    assert hits, "검색 결과가 없습니다"
    assert hits[0].score >= hits[-1].score
    assert all(h.why for h in hits), "왜 걸렸는지 설명이 없습니다"


def test_search_is_deterministic(doc):
    idx = chunk_search.ChunkIndex(doc)
    a = [h.chunk.chunk_id for h in idx.search(["신탁금액"], top=5)]
    b = [h.chunk.chunk_id for h in idx.search(["신탁금액"], top=5)]
    assert a == b


def test_refs_expansion_stays_scoped(doc, onto):
    """별지 참조가 별지 전체를 끌어오면 컨텍스트가 망가진다 — 조 단위로 좁혀야 한다."""
    idx = chunk_search.ChunkIndex(doc)
    hits = idx.search(["신탁금액"], top=2)
    if not hits:
        pytest.skip("검색 결과 없음")
    extra = chunk_search.expand_refs(doc, hits, onto)
    assert len(extra) <= len(doc.chunks) // 2, f"참조 확장이 과합니다: {len(extra)}건"
    cited = {h.chunk.article for h in hits}
    for c in extra:
        assert c.article in cited or c.article is None


def test_small_to_big_serves_parent_article(doc):
    """항 단위로 걸려도 컨텍스트는 부모 조 전체여야 한다 (§D2-5)."""
    target = next((c for c in doc.chunks if c.level == "항" and c.article), None)
    if target is None:
        pytest.skip("항 단위 청크가 없는 골든 문서")
    served = chunk_search.serve_small_to_big(doc, target)
    assert target.chunk_id in {c.chunk_id for c in served}
    assert all(c.article == target.article for c in served)


def test_no_embeddings_anywhere():
    """§D1 — 임베딩 의존이 들어오면 재현성이 깨진다. 코드에 흔적이 없어야 한다."""
    banned = ("sentence_transformers", "faiss", "chromadb", "openai.embeddings",
              "embed_query", "vectorstore")
    hits = []
    for p in (ROOT / "src").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        for b in banned:
            if b in text:
                hits.append(f"{p.name}:{b}")
    assert not hits, f"임베딩 의존이 발견됐습니다: {hits}"


# ===========================================================================
# 뷰어 번들 — 화면이 읽는 JSON 이 항상 만들어져야 한다
# ===========================================================================

def test_viewer_payload_is_serializable(onto):
    import json as _json

    import cli
    payload = cli._viewer_payload(onto, ROOT)
    assert payload["docs"], "뷰어에 보여줄 chunks 문서가 없습니다"
    assert payload["ontology"]["fields"], "온톨로지 탭이 빌 것입니다"
    for rep in payload["reports"]:
        assert rep["name"] and rep["rows"], f"빈 대사 리포트: {rep['name']}"
        assert rep["firings"], "발화 통계가 번들에 없습니다 (§C12.4 탭이 빔)"
    _json.dumps(payload, ensure_ascii=False)     # date 등 직렬화 불가 값이 없어야 한다


def test_viewer_query_endpoint_shape(onto):
    import cli
    payload = cli._viewer_payload(onto, ROOT)
    golden = next(d for d in payload["docs"] if "golden_pairs" in d["path"])
    r = cli._run_query(golden, "신탁금액이 얼마인가요?", onto)
    assert r["answer"]["found"] and r["answer"]["value"] == "100000000"
    assert r["route"]["path"], "라우팅 경로가 비면 화면에서 왜 그랬는지 못 본다"
