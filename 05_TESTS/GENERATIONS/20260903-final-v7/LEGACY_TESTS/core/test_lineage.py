"""계보 원장 — 파생·조인·낙차의 규약 (docs/LINEAGE.md).

여기서 지키는 것 다섯:
  (1) 조인은 본문 sha256[:16] == doc_id 로만 선다 — 이름 매칭은 없다.
  (2) manifest 두 세대(항목 body_sha256 · role=body 첨부)를 한 규칙으로 읽는다.
  (3) 낙차가 next 로 정직하게 갈린다 — 수집 → 변환(hwp 만) → 구조화 → 없음.
  (4) 고아가 갈린다 — 이름이 수집분에 있으면 낡음(stale), 없으면 수집 밖 유입.
  (5) links.json 의 runs 는 간선 저장·해제가 지나가도 보존된다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core import lineage  # noqa: E402


def _sha(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _put(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def world(tmp_path):
    """수집 두 출처 + 구조화 스토어 + links.json — 낙차가 다 들어 있는 소우주.

    law: A(신형 manifest, 구조화 완료) · B(구형 role=body, 구조화 대기)
    kofia: C(hwp 본문, 사이드카 없음 → 변환 대기) · D(partial → 수집 대기)
    스토어 고아: E(이름이 B 와 같고 sha 다름 → 낡음) · F(수집 밖 유입)
    """
    corpus = tmp_path / "corpus"
    store = tmp_path / "store"
    sha = {k: _sha(k) for k in "ABCEF"}

    _put(corpus / "law" / "manifest.json", {"items": [
        {"name": "A법", "kind": "law", "status": "ok",
         "body_sha256": sha["A"], "body_file": "corpus/law/A/본문.xml",
         "body_format": "xml"},
        {"name": "B법", "kind": "law", "status": "ok", "attachments": [
            {"role": "body", "sha256": sha["B"],
             "file": "corpus/law/B/본문.xml", "actual_format": "xml"},
            {"role": "attachment", "sha256": _sha("B별표"),
             "file": "corpus/law/B/별표.hwp", "actual_format": "hwp5(ole)"}]},
    ]})
    _put(corpus / "kofia" / "manifest.json", {"items": [
        {"name": "C규정", "kind": "kofia-rule", "status": "ok",
         "body_sha256": sha["C"], "body_file": "corpus/kofia/C/전문.hwp",
         "body_format": "hwp5(ole)"},
        {"name": "D규정", "kind": "kofia-rule", "status": "partial",
         "attachments": []},
    ]})

    for key, name in [("A", "A법"), ("E", "B법"), ("F", "업로드 문서")]:
        _put(store / sha[key][:16] / "meta.json",
             {"name": name, "at": "2026-08-13T00:00:00+00:00",
              "passed": True, "score": 1.0, "source_kind": "lawxml"})

    links = tmp_path / "links.json"
    _put(links, {"links": [{"src_doc": sha["A"][:16], "src": 1,
                            "dst_doc": sha["E"][:16], "dst": 2, "via": "LLM"}],
                 "runs": [{"at": "t0", "via": "LLM", "saved": 1}]})
    return {"corpus": corpus, "store": store, "links": links, "sha": sha}


def test_조인은_sha로만_서고_낙차가_next로_갈린다(world):
    led = lineage.build(world["store"], world["links"], world["corpus"])
    by = {i["name"]: i for i in led["items"]}

    # (1)+(2) A 는 신형, B 는 구형인데 같은 규칙으로 본문이 잡힌다
    assert by["A법"]["doc_id"] == world["sha"]["A"][:16]
    assert by["B법"]["doc_id"] == world["sha"]["B"][:16]

    # (3) 낙차: A 완료 → 없음 / B 스토어 없음 → 구조화 / C 사이드카 없음 → 변환
    #     / D 본문 미확보 → 수집. XML 은 변환이 요구되지 않는다.
    assert by["A법"]["next"] is None and by["A법"]["structured"]["passed"] is True
    assert by["B법"]["next"] == "구조화" and by["B법"]["converted"]["required"] is False
    assert by["C규정"]["next"] == "변환"
    assert by["D규정"]["next"] == "수집" and by["D규정"]["doc_id"] is None

    # 경로는 형식이 선언한다 — 'hwp5(ole)' 는 hwp 계열, 'xml' 은 xml 계열.
    # 로직은 달라도 단계 모델은 하나라는 일원화의 자리다 (docs/LINEAGE.md).
    assert by["A법"]["route"]["family"] == "xml"
    assert by["C규정"]["route"]["family"] == "hwp"
    assert by["D규정"]["route"]["family"] is None      # 본문이 없으면 경로도 없다

    # 별표 hwp 첨부는 관문이 아니라 개수로만 병기된다
    assert by["B법"]["converted"] == {"required": False, "annex_hwp": 1,
                                      "annex_md": 0}

    # 확정 간선이 문서별로 세어진다
    assert by["A법"]["linked"] == {"out": 1, "in": 0}

    # 사이드카가 생기면 C 는 구조화 대기로 넘어간다
    md = world["corpus"] / "kofia" / "C" / "전문.hwp.md"
    md.parent.mkdir(parents=True)
    md.write_text("# C", encoding="utf-8")
    led2 = lineage.build(world["store"], world["links"], world["corpus"])
    assert {i["name"]: i for i in led2["items"]}["C규정"]["next"] == "구조화"


def test_고아는_낡음과_수집밖유입으로_갈린다(world):
    led = lineage.build(world["store"], world["links"], world["corpus"])
    extras = {e["doc_id"]: e for e in led["extras"]}
    assert set(extras) == {world["sha"]["E"][:16], world["sha"]["F"][:16]}
    assert extras[world["sha"]["E"][:16]]["stale"] is True     # 이름 "B법" 이 수집분에 있다
    assert extras[world["sha"]["F"][:16]]["stale"] is False


def test_깔때기_요약이_출처별로_접힌다(world):
    s = lineage.summary(lineage.build(world["store"], world["links"],
                                      world["corpus"]))
    per = {r["source"]: r for r in s["sources"]}
    assert per["law"] == {"source": "law", "items": 2, "collected": 2,
                          "convert_required": 0, "converted": 0, "structured": 1}
    assert per["kofia"] == {"source": "kofia", "items": 2, "collected": 1,
                            "convert_required": 1, "converted": 0,
                            "structured": 0}
    assert s["extras"] == {"total": 2, "stale": 1}
    assert s["links"]["present"] and s["links"]["edges"] == 1
    assert s["links"]["last_run"]["saved"] == 1


def test_links_없으면_연결국면이_미실행으로_보인다(world):
    led = lineage.build(world["store"], world["links"].parent / "없음.json",
                        world["corpus"])
    assert led["links"] == {"present": False, "edges": 0, "runs": 0,
                            "last_run": None}


def test_간선_저장과_해제가_runs_를_보존한다(world, monkeypatch):
    """(5) — settle 이력은 연결 국면의 자기 기록이라, 간선을 덧붙이거나
    지우는 손이 지나가도 남아야 한다."""
    pytest.importorskip("fastapi", reason="FastAPI 필요")
    monkeypatch.setenv("RAG_LINKS_STORE", str(world["links"]))
    from lawrag.api.routers import rag as rag_router

    added = rag_router._save_links([{"src_doc": "x", "src": 1,
                                     "dst_doc": "y", "dst": 2, "via": "사람"}])
    assert added == 1
    rag_router._record_settle_run({"via": "LLM", "pending": 3, "settled": 0,
                                   "saved": 0})

    data = json.loads(world["links"].read_text(encoding="utf-8"))
    assert len(data["links"]) == 2                  # 기존 1 + 추가 1
    assert [r["via"] for r in data["runs"]] == ["LLM", "LLM"]
    assert data["runs"][0]["at"] == "t0"            # 기존 이력이 남아 있다
    assert data["runs"][1]["saved"] == 0            # 0건 확정도 실행 사실은 남는다
