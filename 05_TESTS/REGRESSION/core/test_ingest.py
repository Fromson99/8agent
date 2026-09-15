"""문서 인제스트의 문(lawrag/core/ingest.py) — 일원화 규약.

여기서 지키는 것 셋:
  (1) 어휘 일치 — 실행부(EXT_FAMILY 계열)와 경로 선언(lineage.ROUTES)은 같은
      계열 어휘를 쓴다. 한쪽에만 있는 계열은 선언 없는 실행이거나 실행 없는
      선언이다 — 둘 다 거짓말이다.
  (2) 모르는 형식은 조용히 아는 척하지 않는다 — None/ValueError 로 선다.
  (3) xml 이 문을 지나면 스토어 규약(doc_id=sha[:16] · source.xml 보존 ·
      meta/result · 멱등 · 폴더 등록부)이 성립한다 — 업로드 API 와 CLI 가
      같은 결과를 내는 근거다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core import ingest, legal_generation, lineage  # noqa: E402

FIX = ROOT / "05_TESTS" / "REGRESSION" / "fixtures" / "law_crawler" / "lawgo"


def test_실행부와_경로선언은_같은_계열_어휘를_쓴다():
    assert set(ingest.EXT_FAMILY.values()) == set(lineage.ROUTES), (
        "lawrag.core.ingest 의 계열과 core.lineage.ROUTES 선언이 어긋났다 — "
        "새 형식은 두 곳에 함께 늘어야 한다 (docs/LINEAGE.md)")


def test_계열_판정은_확장자_대소문자를_가리지_않는다():
    assert ingest.family_of("A법 본문.XML") == "xml"
    assert ingest.family_of("전문.HWP") == "hwp"
    assert ingest.family_of("문서.hwpx") == "hwp"
    assert ingest.family_of("보고서.docx") == "docx"
    assert ingest.family_of("스캔.pdf") == "pdf"
    assert ingest.family_of("모름.txt") is None
    assert ingest.family_of("") is None


def test_모르는_형식은_문에서_선다(tmp_path):
    with pytest.raises(ValueError):
        ingest.ingest(b"x", "메모.txt", store=tmp_path)


def test_xml_이_문을_지나면_스토어_규약이_성립한다(tmp_path):
    raw = (FIX / "law_body_full_excerpt.xml").read_bytes()
    store = tmp_path / "store"

    r = ingest.ingest(raw, "자본시장과 금융투자업에 관한 법률 본문.xml",
                      store=store, name="자본시장법", folder="법령")

    doc_id = hashlib.sha256(raw).hexdigest()[:16]
    assert r["doc_id"] == doc_id                       # 조인 키 — 원장이 이 값으로 잇는다
    d = store / doc_id
    assert (d / "source.xml").read_bytes() == raw      # 원본 보존 — 재이관의 정본
    assert (d / "source.pdf").exists() and (d / "result.json").exists()

    meta = json.loads((d / "meta.json").read_text("utf-8"))
    assert meta["source_kind"] == "lawxml"
    assert meta["name"] == "자본시장법"
    assert meta["folder"] == "법령"
    result = json.loads((d / "result.json").read_text("utf-8"))
    assert result["coordinate_schema_version"] == "legal-coordinate-v2"
    article = next(node for node in result["nodes"]
                   if node.get("family") == "kr_article"
                   and node.get("coordinate_scope") == "body")
    assert article["legal_coordinate"]["surface"] == article["surface"]
    assert article["coordinate_key"] == f"body:{article['surface']}"
    descendant = next(node for node in result["nodes"]
                      if node.get("coordinate_scope") == "body"
                      and (node.get("legal_coordinate") or {}).get("chain"))
    assert descendant["coordinate_key"] == (
        f"body:{descendant['legal_coordinate']['surface']}")
    # 폴더 등록부 — 업로드·CLI·PATCH 가 같은 파일을 쓴다 (register_folder 하나)
    folders = json.loads((store / "folders.json").read_text("utf-8"))["folders"]
    assert "법령" in folders

    # 멱등 — 같은 바이트는 같은 doc_id 로 제자리 갱신되고, 사람이 고친 이름을 지킨다
    meta["name"] = "사람이 고친 이름"
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    r2 = ingest.ingest(raw, "자본시장과 금융투자업에 관한 법률 본문.xml",
                       store=store, name="자본시장법")
    assert r2["doc_id"] == doc_id
    assert r2["meta"]["name"] == "사람이 고친 이름"


def test_공식_법령의_현행은_인제스트_순서가_아니라_generation이_정한다(tmp_path):
    raw = (FIX / "law_body_full_excerpt.xml").read_bytes()
    store = tmp_path / "store"
    old = ingest.ingest_lawxml_bytes(
        raw, "시험법", store, "법령", {"kind": "law", "law_serial": "1"})
    # XML 파서가 받아들일 수 있는 범위에서 내용을 바꿔 새 해시를 만든다.
    newer_raw = raw.replace(b"</\xeb\xb2\x95\xeb\xa0\xb9>", b"<!-- revision --></\xeb\xb2\x95\xeb\xa0\xb9>")
    new = ingest.ingest_lawxml_bytes(
        newer_raw, "시험법", store, "법령", {"kind": "law", "law_serial": "2"})

    old_meta = json.loads((store / old["doc_id"] / "meta.json").read_text("utf-8"))
    new_meta = json.loads((store / new["doc_id"] / "meta.json").read_text("utf-8"))
    assert old_meta["status"] == new_meta["status"] == "미확정"
    assert old_meta["series"] == new_meta["series"] == "시험법"

    # 나중에 들어온 파일이 아니라 manifest가 고른 old를 canonical로 삼는다.
    contract = legal_generation.build_contract({
        "authority_as_of": "20260827",
        "items": [{
            "name": "시험법", "kind": "law", "status": "ok",
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "authority_mode": "effective-current",
            "authority_as_of": "20260827",
        }],
    })
    sync = legal_generation.synchronize_structure(store, contract)
    old_meta = json.loads((store / old["doc_id"] / "meta.json").read_text("utf-8"))
    new_meta = json.loads((store / new["doc_id"] / "meta.json").read_text("utf-8"))
    assert old_meta["status"] == "현행" and old_meta["canonical"] is True
    assert new_meta["status"] == "구판" and new_meta["canonical"] is False
    assert old_meta["authority_generation"] == new_meta["authority_generation"]
    assert sync["current"] == 1 and sync["old"] == 1
