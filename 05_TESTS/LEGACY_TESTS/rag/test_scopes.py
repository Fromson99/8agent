"""질의 스코프 — "이 문서들만 대상으로" 의 계약을 시험한다 (2026-08-19 과제 1).

    · 진입(제목·용어·본문·벡터·기억·회복)은 스코프 안에서만
    · 동반(배제·위임·준용·수임·정의·제재·참조·항해)은 밖으로 나가되 scope_out 표식
    · 스코프 정의는 yml — 파일명(확장자·' 본문' 꼬리)로 적어도 스토어 이름과 맞는다
    · 못 찾은 이름은 조용히 버리지 않고 missing 으로 보인다
    · 내규(kind=internal)·구판(status=구판)은 태그로 갈린다 — 기본 스코프는 구판 제외

모델 없이 돈다 — 벡터는 가짜 npz, 질의 임베딩은 monkeypatch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import answer as answer_mod                 # noqa: E402
from lawrag.core.rag import scopes as scopes_mod                 # noqa: E402
from lawrag.core.rag import vector as vector_mod                 # noqa: E402
from lawrag.core.rag import vecfirst                             # noqa: E402
from lawrag.core.rag.index import Index, scope_kind_of          # noqa: E402
from lawrag.core.rag.search import search                        # noqa: E402


# ---------------------------------------------------------------- 재료
def _doc(doc_id, name, title2, meta_extra=None, ref_text="제2조를 따른다"):
    nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "총칙", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": title2, "page": 1, "span": [1, 2]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": ref_text, "kind": "text"},
        {"idx": 1, "page": 1, "text": f"{title2}에 관한 본문이다", "kind": "text"},
    ]
    meta = {"name": name, **(meta_extra or {})}
    return (doc_id, meta, {"nodes": nodes, "blocks": blocks})


def _docs():
    return [
        _doc("dA", "자본시장과 금융투자업에 관한 법률", "설명의무", {"kind": "law"}),
        _doc("dB", "자본시장과 금융투자업에 관한 법률 시행령", "설명의무 세부", {"kind": "law"}),
        _doc("dN", "위험관리기준시행세칙", "위험한도", {"kind": "internal", "status": "현행",
                                                   "series": "위험관리기준시행세칙", "version": "v2"}),
        _doc("dO", "위험관리기준시행세칙 v1", "위험한도 구판", {"kind": "internal", "status": "구판",
                                                      "series": "위험관리기준시행세칙", "version": "v1"}),
        _doc("dF", "상장예비심사신청서 서식-1", "서식 항목", {"kind": "krx-form"}),
    ]


def _index():
    idx = Index.from_docs(_docs())
    # 간선을 직접 심는다 — dA 제2조 본문이 dB 제2조를 가리킨다(문서 사이 참조).
    idx._refs = {d: [] for d in idx.docs}
    idx._cross = ([{"src_doc": "dA", "src": 2, "dst_doc": "dB", "dst": 2,
                    "surface": "시행령 제2조", "block": 1, "rel": "인용"}], [])
    return idx


def _arm_vector(tmp_path, monkeypatch, qvec):
    d = tmp_path / "sections"
    d.mkdir(parents=True, exist_ok=True)
    rows = [("dA", 2), ("dB", 2), ("dN", 2), ("dO", 2), ("dF", 2)]
    # dB 가 가장 가깝고 dA 는 둘째 — 스코프가 dA 만이면 dB 가 진입을 먹으면 안 된다
    vecs = [[0.8, 0.6], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.5, 0.5]]
    np.savez_compressed(d / "vectors.npz", v=np.array(vecs, dtype=np.float16))
    with (d / "meta.jsonl").open("w", encoding="utf-8") as f:
        for doc_id, node in rows:
            f.write(json.dumps({"doc_id": doc_id, "node": node}) + "\n")
    monkeypatch.setenv("RAG_VECTOR_STORE", str(d))
    vector_mod._cache.clear()
    from lawrag.core import embedding
    monkeypatch.setattr(embedding, "available", lambda: True)
    monkeypatch.setattr(embedding, "encode_one",
                        lambda q: np.array(qvec, dtype=np.float32))


# ---------------------------------------------------------------- 태그 축
def test_kind_는_내규_외규_서식_축으로_접힌다():
    assert scope_kind_of("internal") == "내규"
    assert scope_kind_of("law") == "외규" and scope_kind_of("admrul") == "외규"
    assert scope_kind_of("krx-rule") == "외규"
    assert scope_kind_of("krx-form") == "서식" and scope_kind_of("klca-model") == "서식"
    assert scope_kind_of("") == "외규"            # 태그 없는 옛 문서는 외규


def test_DocView_가_meta_태그를_읽는다():
    idx = _index()
    v = idx.docs["dN"]
    assert (v.kind, v.status, v.series, v.version) == ("internal", "현행", "위험관리기준시행세칙", "v2")
    assert v.scope_kind == "내규" and v.is_current
    assert not idx.docs["dO"].is_current
    assert idx.docs["dA"].scope_kind == "외규" and idx.docs["dA"].is_current


# ---------------------------------------------------------------- 색인 스코프
def test_기본_스코프는_구판만_뺀다():
    idx = _index()
    sub = idx.scoped(None)
    assert sub.scope is not None and "dO" not in sub.scope
    assert {"dA", "dB", "dN", "dF"} <= sub.scope
    # 구판이 없는 스토어면 제한이 없다(비용 0)
    idx2 = Index.from_docs([d for d in _docs() if d[0] != "dO"])
    assert idx2.scoped(None) is idx2


def test_공식_generation은_meta가_stale해도_noncanonical_법령판을_뺀다():
    docs = [
        _doc("law-current", "시험법", "현재", {"kind": "law", "status": "현행"}),
        _doc("law-stale", "시험법", "옛판", {"kind": "law", "status": "현행"}),
        _doc("rule", "민간규정", "규정", {"kind": "krx-rule"}),
    ]
    idx = Index.from_docs(
        docs, canonical_doc_ids={"law-current"},
        authority_generation="g1", authority_as_of="20260827")
    sub = idx.scoped(None)
    assert sub.scope == frozenset({"law-current", "rule"})
    assert "law-stale" not in sub.entry_docs


def test_스코프_색인은_진입_표면형만_거르고_docs_는_전부_든다():
    idx = _index()
    sub = idx.scoped({"dA"}, name="A만")
    assert set(sub.docs) == set(idx.docs)                 # 좌표 되짚기는 전부
    assert {e.doc_id for e in sub.entries} == {"dA"}     # 진입은 안만
    assert set(sub.entry_docs) == {"dA"}
    assert sub.in_scope("dA") and not sub.in_scope("dB")
    # 어휘 검색 — "설명의무 세부" 는 dB 제목인데 스코프 밖이라 안 걸린다
    r = search(sub, "설명의무 세부 알려줘")
    assert all(h.doc_id == "dA" for h in r.hits)
    r_all = search(idx, "설명의무 세부 알려줘")
    assert any(h.doc_id == "dB" for h in r_all.hits)


def test_본문_색인도_스코프_안만():
    idx = _index()
    sub = idx.scoped({"dN"})
    post = sub.postings()
    assert all(doc == "dN" for docs in post.values() for (doc, _) in docs)


# ---------------------------------------------------------------- 벡터
def test_벡터_진입은_스코프_안에서만_경쟁한다(tmp_path, monkeypatch):
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])
    # 전체: dB(코사인 1.0)가 1위
    assert vector_mod.search("q", topk=2)[0][0] == "dB"
    # 스코프 dA: dB 행은 경쟁에서 빠지고 dA 가 1위
    out = vector_mod.search("q", topk=2, doc_ids=frozenset({"dA"}))
    assert [o[0] for o in out] == ["dA"]


def test_벡터우선_회수_진입은_안_동반은_밖으로_표식(tmp_path, monkeypatch):
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])
    idx = _index()
    sub = idx.scoped({"dA"}, name="A만")
    secs, meta = vecfirst.retrieve(sub, "설명의무", entry_k=2)
    secs, smeta = answer_mod.enforce_scope(sub, secs)
    entries = [s for s in secs if not s.is_companion]
    assert entries and all(s.doc_id == "dA" for s in entries)
    # dA 제2조 → dB 제2조 참조가 동반으로 따라왔고 표식이 붙었다
    comp = [s for s in secs if s.doc_id == "dB"]
    assert comp and all(s.is_companion and s.scope_out for s in comp)
    assert smeta["out"] == len(comp) and smeta["dropped"] == []
    assert comp[0].cite()["scope_out"] is True
    # 컨텍스트 머리에도 표식이 선다
    assert "질의 범위 밖 문서" in answer_mod._context_text(secs)


def test_enforce_scope_는_밖_진입을_버리고_번호를_다시_맨다():
    idx = _index()
    sub = idx.scoped({"dA"})
    from lawrag.core.rag.answer import Section
    secs = [Section(n=1, doc_id="dB", doc="B", node=2, path="제2조", page=1,
                    kind="벡터", matched="코사인 0.9"),
            Section(n=2, doc_id="dA", doc="A", node=1, path="제1조", page=1,
                    kind="벡터", matched="코사인 0.8"),
            Section(n=3, doc_id="dB", doc="B", node=2, path="제2조", page=1,
                    kind="참조", matched="→", ref_src={"doc_id": "dA", "node": 1})]
    kept, meta = answer_mod.enforce_scope(sub, secs)
    assert [(s.doc_id, s.n) for s in kept] == [("dA", 1), ("dB", 2)]
    assert meta["dropped"][0]["doc_id"] == "dB" and meta["out"] == 1
    # 스코프 없는 색인은 아무것도 안 한다
    kept2, meta2 = answer_mod.enforce_scope(idx, list(secs))
    assert len(kept2) == 3 and meta2 == {"dropped": [], "out": 0}


# ---------------------------------------------------------------- yml 정의
def _write_yml(tmp_path, monkeypatch, text):
    p = tmp_path / "scopes.yml"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setenv("RAG_SCOPES_FILE", str(p))
    scopes_mod._cache.clear()
    return p


def test_파일명으로_적은_스코프가_스토어_이름에_맞는다(tmp_path, monkeypatch):
    _write_yml(tmp_path, monkeypatch, """
scopes:
  - name: 자본시장-기본
    description: 법+시행령
    documents:
      - 자본시장과 금융투자업에 관한 법률 본문.xml
      - "자본시장과  금융투자업에 관한 법률 시행령"
      - 없는문서.pdf
""")
    idx = _index()
    r = scopes_mod.resolve(idx, "자본시장-기본")
    assert r is not None and r.doc_ids == frozenset({"dA", "dB"})
    assert r.missing == ["없는문서.pdf"]            # 조용히 안 버린다
    rows = scopes_mod.listing(idx)
    me = next(x for x in rows if x["name"] == "자본시장-기본")
    assert me["count"] == 2 and me["missing"] == ["없는문서.pdf"]
    # 내장 셋도 같이 나온다
    assert {x["name"] for x in rows} >= {"외규", "내규", "서식"}


def test_태그로_묶는_스코프와_내장_스코프(tmp_path, monkeypatch):
    _write_yml(tmp_path, monkeypatch, """
scopes:
  - name: 법률만
    kinds: [law]
  - name: 내규-전부
    scope_kinds: [내규]
    include_old: true
""")
    idx = _index()
    assert scopes_mod.resolve(idx, "법률만").doc_ids == frozenset({"dA", "dB"})
    assert scopes_mod.resolve(idx, "내규-전부").doc_ids == frozenset({"dN", "dO"})
    # 내장: 외규는 서식·내규를 뺀 현행 전부, 내규는 현행만(구판 제외)
    assert scopes_mod.resolve(idx, "외규").doc_ids == frozenset({"dA", "dB"})
    assert scopes_mod.resolve(idx, "내규").doc_ids == frozenset({"dN"})
    assert scopes_mod.resolve(idx, "서식").doc_ids == frozenset({"dF"})
    assert scopes_mod.resolve(idx, "없는이름") is None


def test_apply_는_이름_합집합이고_빈_스코프는_예외(tmp_path, monkeypatch):
    _write_yml(tmp_path, monkeypatch, "scopes:\n  - name: A\n    documents: [자본시장과 금융투자업에 관한 법률]\n")
    idx = _index()
    sub, info = scopes_mod.apply(idx, "A", ["위험관리기준시행세칙.docx"])
    assert sub.scope == frozenset({"dA", "dN"}) and sub.scope_name == "A"
    assert info["names"] == sorted(["자본시장과 금융투자업에 관한 법률", "위험관리기준시행세칙"])
    import pytest
    with pytest.raises(ValueError):
        scopes_mod.apply(idx, "모르는스코프", None)
    with pytest.raises(ValueError):
        scopes_mod.apply(idx, "", ["전혀없는문서"])
    # 둘 다 비면 기본(구판 제외)
    sub0, info0 = scopes_mod.apply(idx, "", None)
    assert info0.get("default") and "dO" not in sub0.scope


def test_yml_을_고치면_재시작_없이_반영(tmp_path, monkeypatch):
    p = _write_yml(tmp_path, monkeypatch, "scopes:\n  - name: A\n    documents: [자본시장과 금융투자업에 관한 법률]\n")
    idx = _index()
    assert scopes_mod.resolve(idx, "A").doc_ids == frozenset({"dA"})
    import os, time
    p.write_text("scopes:\n  - name: A\n    documents: [자본시장과 금융투자업에 관한 법률 시행령]\n", encoding="utf-8")
    os.utime(p, (time.time() + 2, time.time() + 2))
    assert scopes_mod.resolve(idx, "A").doc_ids == frozenset({"dB"})


# ---------------------------------------------------------------- API
def test_ask_와_search_가_스코프를_받는다(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from lawrag.api.routers import rag as rag_router
    from lawrag.core.rag import index as index_mod

    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    _write_yml(tmp_path, monkeypatch, "scopes:\n  - name: A\n    documents: [자본시장과 금융투자업에 관한 법률]\n")
    idx = _index()
    monkeypatch.setattr(index_mod, "current", lambda: idx)
    app = FastAPI()
    app.include_router(rag_router.router)
    c = TestClient(app)

    rows = c.get("/v1/rag/scopes").json()["scopes"]
    assert next(x for x in rows if x["name"] == "A")["count"] == 1
    # 모르는 스코프는 400 — 조용히 전체를 뒤지지 않는다
    assert c.post("/v1/rag/ask", json={"question": "설명의무", "scope": "없음"}).status_code == 400
    assert c.get("/v1/rag/search", params={"q": "설명의무 세부", "scope": "없음"}).status_code == 400
    # 어휘 검색(auto)에 스코프 — dB 제목이 안 걸린다
    r = c.get("/v1/rag/search", params={"q": "설명의무 세부", "scope": "A"}).json()
    assert r["scope"]["name"] == "A" and r["documents"] == 1
    assert all(h["doc_id"] == "dA" for h in r["hits"])
    # yml 교체 업로드 — 모양이 틀리면 400, 맞으면 다음 호출부터 반영
    bad = c.post("/v1/rag/scopes/file", files={"file": ("s.yml", b"scopes: 3", "text/yaml")})
    assert bad.status_code == 400
    ok = c.post("/v1/rag/scopes/file", files={"file": (
        "s.yml", "scopes:\n  - name: B\n    documents: [자본시장과 금융투자업에 관한 법률 시행령]\n".encode(), "text/yaml")})
    assert ok.status_code == 200
    assert next(x for x in ok.json()["scopes"] if x["name"] == "B")["count"] == 1
