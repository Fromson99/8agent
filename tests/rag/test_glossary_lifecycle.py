"""용어집 라우터의 생애주기 — 마이그레이션·강등·표면형 재훑기의 계약.

라우터 모듈의 경로 상수(TERMS_FILE·STORE)를 갈아끼워 시험한다 —
함수들이 모듈 전역을 참조하므로 임시 경로로 격리된다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.routers import glossary as g                       # noqa: E402


def _isolate(tmp_path, monkeypatch, terms=None):
    store = tmp_path / "store"
    store.mkdir()
    tf = tmp_path / "glossary.json"
    if terms is not None:
        tf.write_text(json.dumps({"terms": terms}, ensure_ascii=False),
                      encoding="utf-8")
    monkeypatch.setattr(g, "STORE", store)
    monkeypatch.setattr(g, "TERMS_FILE", tf)
    return store, tf


def _doc(store):
    d = store / "doc1"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"name": "A.pdf"}), encoding="utf-8")
    (d / "result.json").write_text(json.dumps({
        "nodes": [{"id": 1, "parent": None, "level": 1, "surface": "제1조",
                   "title": "안전장치", "page": 1, "span": [0, 1], "block": 0}],
        "blocks": [{"idx": 0, "page": 1, "kind": "text",
                    "text": "안전밸브(PSV)는 압력을 낮춘다"}],
    }, ensure_ascii=False), encoding="utf-8")


def test_옛_파일은_읽을_때_생애주기가_채워진다(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, terms=[
        {"term": "안전밸브", "key": "안전밸브", "surfaces": ["안전밸브"],
         "source": "user", "occurrences": []}])
    row = g._load_user()["안전밸브"]
    assert row["source"] == "수기"          # user → 수기 정규화
    assert row["status"] == "활성"
    assert row["hits"] == 0


def test_강등은_수기만_실삭제_나머지는_tombstone(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, terms=[
        {"term": "수기용어", "key": "수기용어", "surfaces": ["수기용어"],
         "source": "수기", "occurrences": []},
        {"term": "전사용어", "key": "전사용어", "surfaces": ["전사용어"],
         "source": "tier1", "occurrences": []}])
    assert g.del_term("수기용어")["action"] == "삭제"
    assert g.del_term("전사용어")["action"] == "tombstone"
    rows = g._load_user()
    assert "수기용어" not in rows
    assert rows["전사용어"]["status"] == "tombstone"


def test_재훑기는_별칭_표면형까지_본다(tmp_path, monkeypatch):
    store, _ = _isolate(tmp_path, monkeypatch, terms=[
        {"term": "안전한밸브장치", "key": "안전한밸브장치",
         "surfaces": ["안전한밸브장치", "PSV"], "source": "tier1",
         "status": "활성", "occurrences": []}])
    _doc(store)
    g.rescan()
    row = g._load_user()["안전한밸브장치"]
    # 본용어 표기는 본문에 없지만 별칭 PSV 가 있다 — 출현이 잡혀야 한다
    assert len(row["occurrences"]) == 1
    assert row["scope"]["docs"] == ["doc1"]


def test_tombstone_은_기본_목록에서_빠진다(tmp_path, monkeypatch):
    store, _ = _isolate(tmp_path, monkeypatch, terms=[
        {"term": "죽은용어", "key": "죽은용어", "surfaces": ["죽은용어"],
         "source": "tier1", "status": "tombstone", "occurrences": []}])
    _doc(store)
    # FastAPI 데코레이터 없이 직접 부르므로 Query 기본값을 명시한다
    alive = {r["term"] for r in
             g.glossary(shared_only=False, q=None, include_dead=False)["terms"]}
    assert "죽은용어" not in alive
    dead = {r["term"] for r in
            g.glossary(shared_only=False, q=None, include_dead=True)["terms"]}
    assert "죽은용어" in dead
