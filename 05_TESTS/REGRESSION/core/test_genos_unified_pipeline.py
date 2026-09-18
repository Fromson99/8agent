import hashlib
import json
from pathlib import Path


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_source_hashes_binds_the_body_selected_by_ingest(tmp_path, monkeypatch):
    from lawrag.pipeline import genos_unified

    body = tmp_path / "corpus/krx/rule/body.html"
    body.parent.mkdir(parents=True)
    body.write_bytes(b"the html body selected by ingest")
    source_sha256 = hashlib.sha256(body.read_bytes()).hexdigest()
    _write_json(
        tmp_path / "corpus/krx/manifest.json",
        {
            "items": [
                {
                    "name": "거래소 규정",
                    "status": "ok",
                    "body_sha256": "1" * 64,
                    "body_html_file": str(body),
                },
            ],
        },
    )
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))

    assert genos_unified._source_hashes(tmp_path) == {
        source_sha256[:16]: source_sha256,
    }


def test_source_hashes_derives_partial_body_coordinate(tmp_path, monkeypatch):
    from lawrag.pipeline import genos_unified

    body = tmp_path / "corpus/kofia/rule/body.html"
    body.parent.mkdir(parents=True)
    body.write_bytes(b"usable partial body")
    source_sha256 = hashlib.sha256(body.read_bytes()).hexdigest()
    _write_json(
        tmp_path / "corpus/kofia/manifest.json",
        {
            "items": [
                {
                    "name": "부분 수집 규정",
                    "status": "partial",
                    "body_html_file": str(body),
                },
                {
                    "name": "실패한 원본",
                    "status": "error",
                    "body_html_file": str(tmp_path / "missing.html"),
                },
            ],
        },
    )
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))

    assert genos_unified._source_hashes(tmp_path) == {
        source_sha256[:16]: source_sha256,
    }


def test_source_only_publish_uses_fresh_common_structure(tmp_path, monkeypatch, term_glossary):
    from lawrag.pipeline import genos_unified
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.storage import Store

    source = tmp_path / "corpus/uploads/internal.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"internal source bytes")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    document_id = source_sha256[:16]
    _write_json(
        tmp_path / "corpus/uploads/manifest.json",
        {
            "source": "uploads",
            "items": [
                {
                    "doc_id": document_id,
                    "body_sha256": source_sha256,
                    "body_file": str(source),
                }
            ],
        },
    )
    structure = tmp_path / "structure" / document_id
    _write_json(
        structure / "meta.json",
        {"doc_id": document_id, "name": "내부규정", "passed": True},
    )
    _write_json(
        structure / "result.json",
        {
            "nodes": [
                {
                    "id": 0,
                    "parent": None,
                    "span": [0, 1],
                    "surface": "제1조",
                    "title": "목적",
                    "family": "kr_article",
                    "block": 0,
                }
            ],
            "blocks": [
                {
                    "idx": 0,
                    "node": 0,
                    "text": "위험관리 기준을 정한다.",
                }
            ],
        },
    )
    monkeypatch.setenv("GENOS_DATA_ROOT", str(tmp_path))
    from lawrag.pipeline import glossary_linking
    monkeypatch.setattr(glossary_linking, "configured", lambda *a: term_glossary)
    result = genos_unified.publish_source_only(data_root=tmp_path)

    assert result["ok"] is True
    assert result["documents"] == 1
    assert set(result["manifest"]["counts"]) == {"document", "source_unit", "source_block"}
    assert result["manifest"]["glossary"]
    assert result["manifest"]["scope"]["document_version_ids"] == [document_id]
    assert json.loads((tmp_path / "generations/CURRENT.json").read_text())["path"] == result["generation"]

    store = Store(result["generation"])
    try:
        pipeline = Pipeline(genos_unified.ROOT, store)
        plan = pipeline.plan("위험관리 기준")
        retrieval = pipeline.retrieve(plan, use_llm=False)
        assert retrieval["term_agent"]["status"] == "METADATA_ONLY"
        assert not retrieval["candidates"]
        assert store.source(document_id, "0")["text"] == "위험관리 기준을 정한다."
    finally:
        store.close()
