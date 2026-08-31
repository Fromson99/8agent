"""판정 지문 — 답변 시점 LLM 판단이 기록되고, 사람 승인만 규칙이 되는 계약.

    지문(discard)은 닫힌 번호 검증을 거쳐 좌표·간선이 붙는다 (모델은 번호만)
    승인 전에는 아무것도 안 바뀐다 · 승인 = 참조 닫힘에서 그 간선 제외
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import answer as answer_mod                   # noqa: E402
from lawrag.core.rag import verdicts                               # noqa: E402
from lawrag.core.rag.answer import Section                         # noqa: E402
from lawrag.core.rag.index import Index                            # noqa: E402


class FakeLLM:
    """합성 호출 1번을 흉내낸다 — 판정 검증 로직만 시험한다."""
    log = []

    def __init__(self, out):
        self.out = out

    def structured(self, *a, **k):
        return self.out


def _sections():
    return [
        Section(n=1, doc_id="d1", doc="A", node=1, path="제1조", page=1,
                kind="벡터", matched="코사인 0.6", text="본문1"),
        Section(n=2, doc_id="d1", doc="A", node=3, path="제3조 벌칙", page=2,
                kind="참조", matched="제1조 → 제3조", text="본문3",
                ref_src={"doc_id": "d1", "node": 1, "path": "제1조",
                         "surface": "제3조"}),
    ]


def test_답변_콜은_판정하지_않는다():
    """판정이 답변 콜에 있으면 그것을 만드는 시간이 곧 응답 지연이다 — 갈랐다."""
    llm = FakeLLM({"answer": "답", "refs": [1], "answerable": True})
    ans = answer_mod.synthesize(llm, "질문", _sections())
    assert ans.answer == "답" and ans.discards == []
    assert "discard" not in answer_mod.ANSWER_SCHEMA["properties"]
    assert "refs" not in answer_mod.ANSWER_SCHEMA["properties"]
    assert [(row["doc_id"], row["node"]) for row in ans.refs] == [
        ("d1", 1), ("d1", 3)]


def test_감사는_닫힌_번호에_간선이_붙는다():
    from lawrag.core.rag import audit as audit_mod

    llm = FakeLLM({"findings": [
        {"n": 2, "kind": "오참조", "reason": "벌칙은 무관"},
        {"n": 1, "kind": "검색무관", "reason": "인용했는데?"},   # 모순 — 버림
        {"n": 99, "kind": "검색무관", "reason": "없는 번호"},    # 밖 — 버림
    ]})
    found = audit_mod.audit(llm, "질문", "답", _sections(), cited={1})
    assert len(found) == 1
    d = found[0]
    assert d["kind"] == "오참조" and d["section"]["node"] == 3
    assert d["ref_src"]["node"] == 1            # 어느 간선이 데려왔는지 좌표로


def test_감사는_경위와_어긋난_판정을_바로잡는다():
    """참조로 오지 않은 구역에 '오참조'를 붙이면 좌표가 없어 백로그가 손댈 데가 없다."""
    from lawrag.core.rag import audit as audit_mod

    llm = FakeLLM({"findings": [
        {"n": 1, "kind": "오참조", "reason": "좌표 틀림"},      # 진입 검색인데 오참조?
        {"n": 2, "kind": "검색무관", "reason": "질문과 무관"},   # 참조로 왔는데 검색무관?
    ]})
    found = {f["n"]: f["kind"] for f in
             audit_mod.audit(llm, "질문", "답", _sections(), cited=set())}
    assert found[1] == "검색무관"      # 참조가 아니면 진입 검색의 결함이다
    assert found[2] == "참조무관"      # 참조로 왔으면 확장의 결함이다


def test_구조화오류는_인용한_구역에도_붙는다():
    """인용했더라도 계층이 틀렸으면 그건 우리 구조화의 결함이다."""
    from lawrag.core.rag import audit as audit_mod

    llm = FakeLLM({"findings": [
        {"n": 1, "kind": "구조화오류", "reason": "제3조가 제1조 자식으로 매달림"}]})
    found = audit_mod.audit(llm, "질문", "답", _sections(), cited={1})
    assert [f["kind"] for f in found] == ["구조화오류"]


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    verdicts._rules_cache.clear()


def test_승인만이_규칙이_된다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = {"kind": "오참조", "reason": "무관", "via": "참조", "matched": "…",
         "section": {"n": 2, "doc_id": "d1", "node": 3, "path": "제3조",
                     "doc": "A", "page": 2},
         "ref_src": {"doc_id": "d1", "node": 1, "path": "제1조", "surface": "제3조"}}
    verdicts.log("q1", "질문", [d])
    verdicts.log("q2", "질문2", [d])

    bl = verdicts.backlog()
    assert len(bl["edges"]) == 1 and bl["edges"][0]["n"] == 2
    edge = bl["edges"][0]["edge"]
    # 지문이 쌓여도 승인 전에는 무반영이다
    assert not verdicts.is_suppressed("d1", 1, "d1", 3)

    verdicts.resolve(edge, "승인", "검수자 확인")
    assert verdicts.is_suppressed("d1", 1, "d1", 3)
    bl2 = verdicts.backlog()
    assert bl2["edges"] == [] and bl2["resolved"] == 1
    # 증거 qid 가 규칙에 남는다 — 왜 억제됐는지 되짚을 수 있다
    import json
    rule = json.loads(verdicts.rules_path().read_text(encoding="utf-8"))
    assert set(rule["suppress"][0]["evidence_qids"]) == {"q1", "q2"}


def test_기각은_기록만_남기고_간선은_산다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # 억제 후보는 오참조뿐이다(무관은 회수 신호) — 처리 계약은 그 위에서 본다
    d = {"kind": "오참조", "reason": "…", "via": "참조", "matched": "…",
         "section": {"n": 2, "doc_id": "d1", "node": 3, "path": "제3조",
                     "doc": "A", "page": 2},
         "ref_src": {"doc_id": "d1", "node": 1, "path": "제1조", "surface": "제3조"}}
    verdicts.log("q1", "질문", [d])
    edge = verdicts.backlog()["edges"][0]["edge"]
    verdicts.resolve(edge, "기각")
    assert not verdicts.is_suppressed("d1", 1, "d1", 3)
    assert verdicts.backlog()["edges"] == []


def test_무관은_억제_후보가_아니다(tmp_path, monkeypatch):
    """좌표가 맞는데 이번 질문에 안 맞은 것("무관")은 회수 신호지 간선의
    잘못이 아니다 — 억제 후보로 올리면 옳은 법령 참조를 영영 잃는다
    (실측: 과태료 6.→제19조제1항 설명의무는 옳은 연결인데 무관 지문이었다)."""
    _iso(tmp_path, monkeypatch)
    base = {"via": "참조", "matched": "6. → 제19조제1항",
            "section": {"n": 2, "doc_id": "d1", "node": 3, "path": "설명의무 ▸ ①",
                        "doc": "금소법", "page": 7},
            "ref_src": {"doc_id": "d1", "node": 1, "path": "과태료 ▸ ① ▸ 6.",
                        "surface": "제19조제1항"}}
    verdicts.log("q1", "채권 중개 준칙과 상충되는 규정", [{**base, "kind": "무관",
                                                          "reason": "질문과 무관"}])
    bl = verdicts.backlog()
    assert bl["edges"] == []                       # 억제 버튼이 붙는 자리에 없다
    assert len(bl["loose"]) == 1                   # 회수 신호로만 남는다
    assert bl["loose"][0]["간선"]["surface"] == "제19조제1항"   # 간선은 보여 준다

    # 오참조는 그대로 억제 후보다 — 좌표가 틀렸다는 판정이니까
    verdicts.log("q2", "설명의무", [{**base, "kind": "오참조", "reason": "좌표가 다르다"}])
    bl2 = verdicts.backlog()
    assert len(bl2["edges"]) == 1 and bl2["edges"][0]["판정"] == {"오참조": 1}


def test_판단_수정은_이력이_남고_수정본이_읽힌다(tmp_path, monkeypatch):
    """LLM 이 오참조라 했는데 실제로는 맞는 연결 — 사람이 판단 JSON 을 고치면
    수정본이 화면의 판단이 되고(백로그에서 빠짐), 원본과 이력은 남는다."""
    _iso(tmp_path, monkeypatch)
    d = {"kind": "오참조", "reason": "무관해 보임", "via": "참조", "matched": "…",
         "section": {"n": 2, "doc_id": "d1", "node": 3, "path": "제3조",
                     "doc": "A", "page": 2},
         "ref_src": {"doc_id": "d1", "node": 1, "path": "제1조", "surface": "제3조"}}
    verdicts.log("q1", "질문", [d])
    assert len(verdicts.backlog()["edges"]) == 1

    verdicts.edit("q1", "지문", 0,
                  {"판정": "정상", "사유": "실제로 맞는 연결이다"}, "검수자 정정")
    assert verdicts.backlog()["edges"] == []          # 정상 — 지문이 아니게 됐다
    m = verdicts.by_qid()["q1"]["지문"][0]
    assert m["판정"] == "정상" and m["사유"] == "실제로 맞는 연결이다"
    assert m["수정이력"][0]["before"]["판정"] == "오참조"   # 원본이 이력에 남는다

    # 허용 밖 필드·없는 대상은 거부된다
    import pytest
    with pytest.raises(ValueError):
        verdicts.edit("q1", "지문", 0, {"엉뚱한필드": 1})
    with pytest.raises(ValueError):
        verdicts.edit("q1", "지문", 9, {"판정": "정상"})


def test_실적은_용어_행에_쌓인다(tmp_path, monkeypatch):
    """인용 → hits, 무관 지문 → misses. 상태는 안 바꾼다 — 세기만 한다."""
    import json

    gl = tmp_path / "glossary.json"
    gl.write_text(json.dumps({"terms": [
        {"term": "안전밸브", "key": "안전밸브", "status": "활성",
         "surfaces": ["안전밸브"], "hits": 0, "misses": 0, "occurrences": []},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("GLOSSARY_STORE", str(gl))

    verdicts.score_terms(["안전밸브"], [])
    verdicts.score_terms([], ["안전밸브"])
    verdicts.score_terms(["없는용어"], [])            # 모르는 키는 조용히 무시
    row = json.loads(gl.read_text(encoding="utf-8"))["terms"][0]
    assert (row["hits"], row["misses"]) == (1, 1)
    assert row["status"] == "활성"                    # 상태는 그대로


def test_억제_간선은_참조_닫힘에서_빠진다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "총칙", "page": 1, "span": [0, 1]},
        {"id": 3, "parent": None, "level": 1, "surface": "제3조",
         "title": "벌칙", "page": 2, "span": [1, 2]},
    ]
    blocks = [{"idx": 0, "page": 1, "text": "제3조를 참고한다", "kind": "text"},
              {"idx": 1, "page": 2, "text": "벌칙", "kind": "text"}]
    idx = Index.from_docs([("d1", {"name": "A"}, {"nodes": nodes, "blocks": blocks})])
    idx._refs = {"d1": [{"src": 1, "dst": 3, "surface": "제3조", "block": 0}]}
    idx._cross = ([], [])
    entry = [Section(n=1, doc_id="d1", doc="A", node=1, path="제1조",
                     page=1, kind="벡터", matched="", text="")]

    grown = answer_mod.expand_refs(idx, list(entry))
    assert any(s.node == 3 for s in grown)              # 억제 전 — 끌려온다

    verdicts.resolve({"src_doc": "d1", "src": 1, "dst_doc": "d1", "dst": 3},
                     "승인", "시험")
    grown2 = answer_mod.expand_refs(idx, list(entry))
    assert not any(s.node == 3 for s in grown2)         # 억제 후 — 건너뛴다


def test_감사는_백그라운드에서_돌고_백로그에_남는다(tmp_path, monkeypatch):
    """답변 스레드는 기다리지 않는다 — 큐에 넣고 워커가 뒤에서 적재한다."""
    from lawrag.core.rag import audit as audit_mod

    _iso(tmp_path, monkeypatch)
    llm = FakeLLM({"findings": [
        {"n": 2, "kind": "오참조", "reason": "벌칙 조항이 아니다"},
        {"n": 1, "kind": "구조화오류", "reason": "항이 앞 조에 붙었다"}]})
    assert audit_mod.submit(llm, "q1", "질문", "답", _sections(), cited=set())
    assert audit_mod.drain(timeout=10), "감사 워커가 큐를 비우지 못했습니다"

    b = verdicts.backlog()
    assert len(b["edges"]) == 1                     # 오참조 → 간선 억제 후보
    assert len(b["struct"]) == 1                    # 구조화오류 → 구역별로 따로
    assert b["struct"][0]["구역"]["node"] == 1


# ---------------------------------------------------------------- 축별 처리
# 판정 넷은 고치는 자리가 다르다. 같은 버튼으로 다루면 옳은 연결을 지우게 된다.

def _miss(kind, with_edge=True):
    r = {"판정": kind, "사유": "이번 질문과 무관", "경위": "참조" if with_edge else "벡터",
         "구역": {"n": 2, "doc_id": "d1", "doc": "A", "node": 3, "path": "제3조"}}
    if with_edge:
        r["간선"] = {"src_doc": "d1", "src": 1, "src_path": "제1조",
                     "surface": "제3조", "dst_doc": "d1", "dst": 3, "dst_path": "제3조"}
    return r


def test_참조무관은_후순위로_밀린다_지우지_않는다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rec = _miss("참조무관")
    verdicts.log("q1", "질문", [{**rec, "kind": "참조무관", "reason": rec["사유"],
                                "section": rec["구역"], "via": "참조",
                                "ref_src": {"doc_id": "d1", "node": 1,
                                            "path": "제1조", "surface": "제3조"}}])
    g = verdicts.backlog()["misses"][0]
    assert g["판정"] == "참조무관"

    verdicts.resolve_miss(g, "후순위", "확장이 넓다")
    assert verdicts.is_demoted("d1", 1, "d1", 3)      # 뒤로 밀린다
    assert not verdicts.is_suppressed("d1", 1, "d1", 3)   # 연결은 산다
    assert verdicts.backlog()["misses"] == []         # 처리돼 백로그에서 내려간다


def test_검색무관은_진입에서만_빠진다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rec = _miss("검색무관", with_edge=False)
    verdicts.log("q1", "질문", [{"kind": "검색무관", "reason": "무관", "via": "벡터",
                                "section": rec["구역"], "ref_src": None}])
    g = verdicts.backlog()["misses"][0]
    verdicts.resolve_miss(g, "진입제외", "벡터가 빗나갔다")
    assert verdicts.is_entry_blocked("d1", 3)         # 진입으로는 안 온다
    assert not verdicts.is_suppressed("d1", 1, "d1", 3)   # 참조로는 여전히 온다


def test_간선_없는_지문은_후순위로_밀_수_없다(tmp_path, monkeypatch):
    import pytest
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="진입제외"):
        verdicts.resolve_miss(_miss("검색무관", with_edge=False), "후순위")


def test_구조화오류는_규칙을_만들지_않고_닫힌다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    sec = {"n": 1, "doc_id": "d1", "doc": "A", "node": 5, "path": "제5조"}
    verdicts.log("q1", "질문", [{"kind": "구조화오류", "reason": "항이 앞 조에 붙음",
                                "section": sec, "via": "벡터", "ref_src": None}])
    b = verdicts.backlog()
    assert len(b["struct"]) == 1 and b["struct"][0]["구역"]["node"] == 5

    verdicts.resolve_struct(sec, "고침", "계층 교정으로 옮김")
    assert verdicts.backlog()["struct"] == []          # 닫힌다
    # 계층은 검수 화면에서 고치는 것이라 억제·진입 규칙이 생기지 않는다
    assert not verdicts.is_entry_blocked("d1", 5)
    assert not verdicts.is_demoted("d1", 1, "d1", 5)


def test_거부된_처리는_기록되지_않는다(tmp_path, monkeypatch):
    """검증 전에 기록하면 거부된 동작도 항목을 백로그에서 내려버린다 —
    사람은 처리했다고 믿는데 아무 규칙도 안 생긴 상태가 된다."""
    import pytest
    _iso(tmp_path, monkeypatch)
    rec = {"kind": "검색무관", "reason": "무관", "via": "벡터", "ref_src": None,
           "section": {"n": 1, "doc_id": "d1", "doc": "A", "node": 3, "path": "제3조"}}
    verdicts.log("q1", "질문", [rec])
    g = verdicts.backlog()["misses"][0]
    with pytest.raises(ValueError):
        verdicts.resolve_miss(g, "후순위")           # 간선이 없다 — 거부
    assert len(verdicts.backlog()["misses"]) == 1    # 여전히 백로그에 있다
