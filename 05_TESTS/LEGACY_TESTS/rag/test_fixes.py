"""착지 교정 — "제2조제3항"을 가리키고 조에 머문 참조를 LLM 이 자손 후보에서
고쳐 앉히고, 사람 승인만이 간선을 실제로 옮기는(재지정 규칙) 계약.

    결정론이 끝까지 내려간 참조는 시험대에 안 오른다 — LLM 은 결함 자리만 본다
    제안은 닫힌 후보(착지의 자손) 안에서만 유효하다
    승인 전에는 간선 무반영 · 승인 = ref_edges 의 도착이 새 좌표로 옮겨 앉는다
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
    log = []

    def __init__(self, out):
        self.out = out
        self.calls = 0

    def structured(self, *a, **k):
        self.calls += 1
        return self.out


def _doc():
    """제2조제3항을 가리키는데, 그 항의 라벨("평가이익의 산정")이 결정론
    문법 밖이라 사슬 하강이 조에 머무는 문서 — 실측 768건의 축소판."""
    return ("d1", {"name": "규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "정의", "page": 1, "span": [1, 4]},
        {"id": 3, "parent": 2, "level": 2, "surface": "평가이익의 산정",
         "title": "", "page": 1, "span": [3, 4]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1조 이 규정은 제2조제3항에 따른다.",
         "kind": "text"},
        {"idx": 1, "page": 1, "text": "제2조(정의) 총론", "kind": "text"},
        {"idx": 2, "page": 1, "text": "② 둘째 항", "kind": "text"},
        {"idx": 3, "page": 1, "text": "③ 평가이익은 다음 각 호와 같이 산정한다.",
         "kind": "text"},
    ]})


def _section(idx):
    """참조 확장이 끌고 온 모양 그대로 — 조에 머문 착지."""
    v = idx.docs["d1"]
    return Section(n=2, doc_id="d1", doc=v.name, node=2, path=v.path(2),
                   page=1, kind="참조", matched="제1조 → 제2조제3항",
                   text=v.section_text(v.by_id[2]),
                   ref_src={"doc_id": "d1", "node": 1, "path": "제1조",
                            "surface": "제2조제3항"})


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    verdicts._rules_cache.clear()


# ------------------------------------------------------------------ 교정 판단
def test_교정은_자손_후보에서_고르고_본문을_바꾼다():
    idx = Index.from_docs([_doc()])
    # 결정론 하강이 실제로 조(2)에 머무는지 — 전제 확인
    assert idx.ref_edges()["d1"][0]["dst"] == 2
    s = _section(idx)
    llm = FakeLLM({"fixes": [{"idx": 0, "node": 3, "reason": "③ 이 제3항이다"}]})
    fixes = answer_mod.repair_landings(llm, idx, [s])
    assert len(fixes) == 1
    f = fixes[0]
    assert (f["dst"], f["new_dst"]) == (2, 3)            # 조 → 그 항
    assert f["src"] == 1 and f["surface"] == "제2조제3항"
    assert s.node == 3 and s.kind == "참조(교정)"        # 이번 답변의 근거가 바뀐다
    assert "평가이익" in s.text


def test_교정_끝까지_내려간_참조는_시험대에_안_오른다():
    """이미 옳게 착지한 간선은 LLM 을 부르지도 않는다 — 결함 자리만 본다."""
    idx = Index.from_docs([_doc()])
    v = idx.docs["d1"]
    s = Section(n=2, doc_id="d1", doc=v.name, node=2, path=v.path(2), page=1,
                kind="참조", matched="제1조 → 제2조",
                text="", ref_src={"doc_id": "d1", "node": 1, "path": "제1조",
                                  "surface": "제2조"})       # 사슬 없음
    llm = FakeLLM({"fixes": []})
    assert answer_mod.repair_landings(llm, idx, [s]) == []
    assert llm.calls == 0


def test_교정_닫힌_후보_밖은_버린다():
    idx = Index.from_docs([_doc()])
    s = _section(idx)
    llm = FakeLLM({"fixes": [{"idx": 0, "node": 99, "reason": "지어냄"}]})
    assert answer_mod.repair_landings(llm, idx, [s]) == []
    assert s.node == 2 and s.kind == "참조"              # 무반영


# ------------------------------------------------------------------ 승인 = 재지정
def test_교정_승인만이_간선을_옮긴다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fix = {"src_doc": "d1", "src": 1, "src_path": "제1조",
           "surface": "제2조제3항", "dst_doc": "d1", "dst": 2,
           "dst_path": "제2조 정의", "new_dst": 3,
           "new_dst_path": "제2조 ▸ 평가이익의 산정", "reason": "③ 이 제3항"}
    verdicts.log_fixes("q1", "질문", [fix])
    verdicts.log_fixes("q2", "질문2", [fix])

    bl = verdicts.backlog()
    assert len(bl["fixes"]) == 1 and bl["fixes"][0]["n"] == 2
    assert bl["fixes"][0]["new_dst"] == 3
    # 승인 전 — 간선은 그대로다
    idx = Index.from_docs([_doc()])
    assert idx.ref_edges()["d1"][0]["dst"] == 2

    verdicts.resolve_fix(fix, "승인", "검수자 확인")
    assert verdicts.redirect_map()[("d1", 1, "d1", 2)]["new_dst"] == 3
    idx2 = Index.from_docs([_doc()])                     # 새 색인 — 재지정 반영
    assert idx2.ref_edges()["d1"][0]["dst"] == 3
    assert verdicts.backlog()["fixes"] == []             # 처리됐다 — 백로그에서 빠짐
    import json
    rule = json.loads(verdicts.rules_path().read_text(encoding="utf-8"))
    assert set(rule["redirect"][0]["evidence_qids"]) == {"q1", "q2"}


def test_교정_기각은_기록만_남기고_간선은_그대로(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fix = {"src_doc": "d1", "src": 1, "surface": "제2조제3항",
           "dst_doc": "d1", "dst": 2, "new_dst": 3, "reason": "…"}
    verdicts.log_fixes("q1", "질문", [fix])
    verdicts.resolve_fix(fix, "기각", "제안이 틀렸다")
    assert verdicts.redirect_map() == {}
    assert verdicts.backlog()["fixes"] == []
    idx = Index.from_docs([_doc()])
    assert idx.ref_edges()["d1"][0]["dst"] == 2


def test_재지정은_새_좌표가_실재할_때만(tmp_path, monkeypatch):
    """구조가 다시 서서 노드가 사라졌으면 — 옛 간선 그대로, 조용히 무시."""
    _iso(tmp_path, monkeypatch)
    fix = {"src_doc": "d1", "src": 1, "surface": "제2조제3항",
           "dst_doc": "d1", "dst": 2, "new_dst": 777, "reason": "…"}
    verdicts.resolve_fix(fix, "승인")
    idx = Index.from_docs([_doc()])
    assert idx.ref_edges()["d1"][0]["dst"] == 2
