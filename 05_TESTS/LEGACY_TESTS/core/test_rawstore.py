"""raw 등록부 — data/corpus 가 원본층이라는 규약 (2026-08-19).

    · 수집기 밖 원본(업로드·inbox·손 반입)은 corpus/<source>/ 사본 + manifest 한 줄
    · 이미 어느 manifest 에 있는 sha 는 다시 등록하지 않는다(사본도 없음)
    · 구조화 문(ingest)이 이 등록을 자동으로 남긴다 — 스토어가 원본의 유일한 자리가 아니게
    · 배치 라인업이 새 출처 manifest(forms·internal…)를 투입 후보로 센다
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core import rawstore   # noqa: E402


def _env(tmp_path, monkeypatch):
    corpus = tmp_path / "data" / "corpus"
    corpus.mkdir(parents=True)
    monkeypatch.setenv("CORPUS_DIR", str(corpus))
    monkeypatch.setenv("STRUCTURE_STORE", str(tmp_path / "data" / "structure"))
    rawstore._cache.clear()
    return corpus


def test_ensure_는_사본과_manifest_한_줄을_남기고_같은_sha_는_다시_안_남긴다(tmp_path, monkeypatch):
    corpus = _env(tmp_path, monkeypatch)
    r = rawstore.ensure(b"hello docx", "규정 안.docx", name="규정안", kind="internal", folder="내규", via="upload")
    assert r["new"] and r["source"] == "uploads"
    p = Path(r["path"])
    assert p.exists() and p.read_bytes() == b"hello docx"
    m = json.loads((corpus / "uploads" / "manifest.json").read_text(encoding="utf-8"))
    it = m["items"][0]
    assert it["body_sha256"] == hashlib.sha256(b"hello docx").hexdigest()
    assert it["body_format"] == "docx" and it["kind"] == "internal" and it["folder"] == "내규"
    assert it["body_file"].startswith("data/corpus/uploads/")       # 저장소 뿌리 상대
    assert it["doc_id"] == it["body_sha256"][:16]
    # 같은 바이트 — 등록도 사본도 늘지 않는다
    r2 = rawstore.ensure(b"hello docx", "다른이름.docx", via="inbox")
    assert not r2["new"] and r2["source"] == "uploads"
    assert len(json.loads((corpus / "uploads" / "manifest.json").read_text(encoding="utf-8"))["items"]) == 1
    assert len(list((corpus / "uploads").rglob("*.docx"))) == 1


def test_수집_manifest_에_이미_있는_원본은_uploads_에_안_쌓인다(tmp_path, monkeypatch):
    corpus = _env(tmp_path, monkeypatch)
    raw = b"<xml>law</xml>"
    (corpus / "law").mkdir()
    (corpus / "law" / "manifest.json").write_text(json.dumps({"source": "law.go.kr", "items": [
        {"name": "어떤 법", "kind": "law", "status": "ok", "body_sha256": hashlib.sha256(raw).hexdigest(),
         "body_file": "data/corpus/law/어떤 법/본문.xml", "body_format": "xml"}]}, ensure_ascii=False), encoding="utf-8")
    rawstore._cache.clear()
    r = rawstore.ensure(raw, "어떤 법 본문.xml", via="upload")
    assert not r["new"] and r["source"] == "law.go.kr" and r["name"] == "어떤 법"
    assert not (corpus / "uploads").exists()


def test_register_files_는_옮기고_사이드카를_같이_들고_manifest_를_만든다(tmp_path, monkeypatch):
    corpus = _env(tmp_path, monkeypatch)
    src = tmp_path / "from_x"
    src.mkdir()
    (src / "서식.hwp").write_bytes(b"hwp bytes")
    (src / "서식.hwp.md").write_text("# md", encoding="utf-8")
    (src / "정관.hwp").write_bytes(b"other")
    sha16 = hashlib.sha256(b"hwp bytes").hexdigest()[:16]
    r = rawstore.register_files([src / "서식.hwp", src / "정관.hwp"], source="forms", kind="krx-form",
                                names={sha16: "상장 서식 A"}, extra={"folder": "상장서식"})
    assert len(r["added"]) == 2 and r["dup"] == []
    assert (corpus / "forms" / "서식.hwp").exists() and (corpus / "forms" / "서식.hwp.md").exists()
    assert not (src / "서식.hwp").exists()                        # 옮겼다
    m = json.loads((corpus / "forms" / "manifest.json").read_text(encoding="utf-8"))
    a = next(i for i in m["items"] if i["orig_filename"] == "서식.hwp")
    assert a["name"] == "상장 서식 A" and a["body_format"] == "hwp5(ole)" and a["folder"] == "상장서식"
    # 다시 등록하면 dup
    (src / "서식2.hwp").write_bytes(b"hwp bytes")
    r2 = rawstore.register_files([src / "서식2.hwp"], source="forms", kind="krx-form")
    assert r2["added"] == [] and r2["dup"][0]["source"] == "forms"


def test_구조화_문이_raw_등록을_자동으로_남긴다(tmp_path, monkeypatch):
    corpus = _env(tmp_path, monkeypatch)
    from lawrag.core import ingest as ingest_mod
    store = tmp_path / "data" / "structure"
    # 무거운 변환은 건너뛴다 — interpret_doc 와 prepare_converted 를 가짜로
    monkeypatch.setattr(ingest_mod, "prepare_converted", lambda d, raw, suffix: (d / "source.pdf"))
    monkeypatch.setattr(ingest_mod, "interpret_doc", lambda pdf, **k: {
        "pages": [], "nodes": [], "blocks": [], "fitness": {"score": 0.9, "passed": True, "tier": "hot"}})
    r = ingest_mod.ingest(b"PK docx", "세칙.docx", store=store, name="세칙", folder="내규",
                          extra_meta={"kind": "internal"}, raw_via="inbox")
    m = json.loads((corpus / "uploads" / "manifest.json").read_text(encoding="utf-8"))
    assert m["items"][0]["doc_id"] == r["doc_id"] and m["items"][0]["via"] == "inbox"
    assert m["items"][0]["kind"] == "internal" and m["items"][0]["folder"] == "내규"


def test_배치_라인업이_새_출처_manifest_를_투입_후보로_센다(tmp_path, monkeypatch):
    corpus = _env(tmp_path, monkeypatch)
    monkeypatch.setenv("PIPELINE_DIR", str(tmp_path / "data" / "pipeline"))
    monkeypatch.setenv("PIPELINE_INBOX", str(tmp_path / "data" / "inbox"))
    (tmp_path / "data" / "structure").mkdir(parents=True)
    f = corpus / "internal"
    f.mkdir()
    (f / "세칙.docx").write_bytes(b"PK internal")
    (f / "manifest.json").write_text(json.dumps({"source": "internal", "items": [
        {"name": "위험관리세칙", "kind": "internal", "status": "ok", "folder": "내규",
         "body_file": str(f / "세칙.docx"), "body_sha256": hashlib.sha256(b"PK internal").hexdigest(),
         "body_format": "docx", "status_label": "현행"},
        {"name": "실패한 것", "kind": "internal", "status": "error", "body_file": str(f / "없음.docx"),
         "body_sha256": "0" * 64, "body_format": "docx"}]}, ensure_ascii=False), encoding="utf-8")
    from lawrag.core import batch as batch_mod
    tg = batch_mod.ingest_targets()
    assert [(t["via"], t["source"], t["name"], t["folder"]) for t in tg] == [("file", "internal", "위험관리세칙", "내규")]
    # 내규 kind 는 내규 문으로 간다
    from lawrag.core import internal_rules
    seen = {}
    monkeypatch.setattr(internal_rules, "ingest_internal_rule",
                        lambda raw, fn, *, store, name="", folder="", status="현행", series="", version="", **k:
                        (seen.update(name=name, status=status) or {"doc_id": "f" * 16}))
    batch_mod._ingest_one(tg[0])
    assert seen == {"name": "위험관리세칙", "status": "현행"}
