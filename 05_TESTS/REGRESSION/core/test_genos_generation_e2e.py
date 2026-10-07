"""The GENOS E2E gate must reject a healthy-looking but unbound fulltext generation."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "genos_generation_e2e", ROOT / "06_TOOLS/COMMANDS/genos_generation_e2e.py")
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "code"
    gen = tmp_path / "generation"
    (gen / "navigation").mkdir(parents=True)
    (gen / "navigation/navigation.sqlite").write_bytes(b"navigation-example")
    nav_sha = CHECK.sha256(gen / "navigation/navigation.sqlite")
    manifest = {
        "schema_version": "term-source-generation-v1", "generation_id": "g1",
        "store_sha256": "a" * 64,
    }
    write(gen / "navigation/manifest.json", {
        "generation_id": "g1", "source_store_sha256": "a" * 64,
        "source_manifest_sha256": CHECK.source_manifest_digest(manifest),
        "index_sha256": nav_sha,
    })
    manifest["navigation"] = {"path": "navigation", "manifest_sha256": CHECK.sha256(gen / "navigation/manifest.json")}
    write(gen / "manifest.json", manifest)
    (gen / "fulltext").mkdir()
    db_path = gen / "fulltext/fulltext.sqlite"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE VIRTUAL TABLE source_fts USING fts5(source_id UNINDEXED, heading, body)")
        db.execute("INSERT INTO source_fts VALUES ('source1', 'heading', 'body')")
    write(gen / "fulltext/manifest.json", {
        "navigation_index_sha256": nav_sha, "source_store_sha256": "a" * 64,
        "fulltext_sha256": CHECK.sha256(db_path),
        "tokenizer": {"name": "pecab", "version": __import__("importlib.metadata", fromlist=["version"]).version("pecab")},
    })
    term = {"implementation": "legal-agent-tools-v5", "fulltext": {
        "path": "fulltext", "navigation_index_sha256": nav_sha,
        "manifest_sha256": CHECK.sha256(gen / "fulltext/manifest.json"),
    }}
    write(root / "00_SYSTEM/PIPELINE.json", {"profiles": {
        "legal-rag": {"nodes": [{"parameters": {"term_agent": term}}]},
        "legal-agent-rag-v5": {"nodes": [{"parameters": {"term_agent": term}}]},
    }})
    return root, gen


def test_matching_generation_fulltext_is_ready(tmp_path, monkeypatch):
    monkeypatch.delenv("GENOS_RAG_IMPLEMENTATION", raising=False)
    root, gen = fixture(tmp_path)
    report = CHECK.audit(root, gen)
    assert report["status"] == "PASS", report
    assert report["generation_id"] == "g1"


def test_unit_fulltext_gate_checks_schema_generation_and_shared_inventory(tmp_path, monkeypatch):
    monkeypatch.delenv('GENOS_RAG_IMPLEMENTATION', raising=False)
    root, gen = fixture(tmp_path)
    (gen / 'fulltext/fulltext.sqlite').unlink()
    path = gen / 'fulltext/units.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body)')
        db.execute("INSERT INTO unit_fts VALUES('u1','body')")
    ft = json.loads((gen / 'fulltext/manifest.json').read_text())
    ft.update(schema_version='semantic-unit-fulltext-v1', generation_id='g1', index_sha256=CHECK.sha256(path))
    write(gen / 'fulltext/manifest.json', ft)
    manifest = json.loads((gen / 'manifest.json').read_text())
    manifest['fulltext'] = {'path': 'fulltext', 'manifest_sha256': CHECK.sha256(gen / 'fulltext/manifest.json'),
                          'navigation_index_sha256': ft['navigation_index_sha256']}
    write(gen / 'manifest.json', manifest)
    write(gen.parent / 'share-receipt.json', {'manifest_sha256': CHECK.sha256(gen / 'manifest.json'),
        'files': {str(p.relative_to(gen)): CHECK.sha256(p) for p in gen.rglob('*') if p.is_file()}})
    assert CHECK.audit(root, gen)['status'] == 'PASS'
    ft['generation_id'] = 'other-generation'
    write(gen / 'fulltext/manifest.json', ft)
    assert any(r['check'] == 'fulltext generation' and r['status'] == 'FAIL' for r in CHECK.audit(root, gen)['checks'])
    ft['schema_version'] = 'unknown'
    write(gen / 'fulltext/manifest.json', ft)
    assert any(r['check'] == 'fulltext schema' and r['status'] == 'FAIL' for r in CHECK.audit(root, gen)['checks'])


def test_generation_binding_overrides_stale_profile_hash(tmp_path, monkeypatch):
    monkeypatch.delenv("GENOS_RAG_IMPLEMENTATION", raising=False)
    root, gen = fixture(tmp_path)
    manifest = json.loads((gen / "manifest.json").read_text())
    nav = json.loads((gen / "navigation/manifest.json").read_text())
    manifest["fulltext"] = {"path": "fulltext",
                            "manifest_sha256": CHECK.sha256(gen / "fulltext/manifest.json"),
                            "navigation_index_sha256": nav["index_sha256"]}
    write(gen / "manifest.json", manifest)
    pipeline = root / "00_SYSTEM/PIPELINE.json"
    config = json.loads(pipeline.read_text())
    config["profiles"]["legal-agent-rag-v5"]["nodes"][0]["parameters"]["term_agent"]["fulltext"]["navigation_index_sha256"] = "0" * 64
    write(pipeline, config)
    assert CHECK.audit(root, gen)["status"] == "PASS"


def test_source_manifest_mismatch_fails_even_when_file_hashes_match(tmp_path, monkeypatch):
    monkeypatch.delenv("GENOS_RAG_IMPLEMENTATION", raising=False)
    root, gen = fixture(tmp_path)
    nav_path = gen / "navigation/manifest.json"
    nav = json.loads(nav_path.read_text())
    nav["source_manifest_sha256"] = "0" * 64
    write(nav_path, nav)
    manifest_path = gen / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["navigation"]["manifest_sha256"] = CHECK.sha256(nav_path)
    write(manifest_path, manifest)
    report = CHECK.audit(root, gen)
    assert report["status"] == "FAIL"
    assert any(row["check"] == "navigation source manifest" and row["status"] == "FAIL"
               for row in report["checks"])


def test_stale_pin_and_missing_index_fail_before_health(tmp_path, monkeypatch):
    monkeypatch.delenv("GENOS_RAG_IMPLEMENTATION", raising=False)
    root, gen = fixture(tmp_path)
    pipeline = root / "00_SYSTEM/PIPELINE.json"
    value = json.loads(pipeline.read_text())
    value["profiles"]["legal-agent-rag-v5"]["nodes"][0]["parameters"]["term_agent"]["fulltext"]["navigation_index_sha256"] = "0" * 64
    write(pipeline, value)
    report = CHECK.audit(root, gen)
    assert report["status"] == "FAIL"
    assert any(r["check"] == "fulltext navigation pin" and r["status"] == "FAIL" for r in report["checks"])
    (gen / "fulltext/fulltext.sqlite").unlink()
    report = CHECK.audit(root, gen)
    assert report["status"] == "FAIL"
    assert any(r["check"] == "fulltext files" and r["status"] == "FAIL" for r in report["checks"])


def test_explicit_generation_must_match_serving_env(tmp_path, monkeypatch):
    _root, gen = fixture(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("GENOS_GENERATION", str(other))
    try:
        CHECK.selected_generation(gen)
    except ValueError as exc:
        assert "differs" in str(exc)
    else:
        raise AssertionError("mismatched serving generation was accepted")


def test_shared_receipt_and_release_must_match_generation(tmp_path, monkeypatch):
    monkeypatch.delenv("GENOS_RAG_IMPLEMENTATION", raising=False)
    root, gen = fixture(tmp_path)
    files = {name: CHECK.sha256(gen / name) for name in (
        "navigation/manifest.json", "navigation/navigation.sqlite",
        "fulltext/manifest.json", "fulltext/fulltext.sqlite")}
    write(gen.parent / "share-receipt.json", {
        "manifest_sha256": CHECK.sha256(gen / "manifest.json"), "files": files,
    })
    assert CHECK.audit(root, gen)["status"] == "PASS"
    files.pop("fulltext/fulltext.sqlite")
    write(gen.parent / "share-receipt.json", {
        "manifest_sha256": CHECK.sha256(gen / "manifest.json"), "files": files,
    })
    assert CHECK.audit(root, gen)["status"] == "FAIL"
    release = tmp_path / "release.json"
    write(release, {"completed": True, "manifest_sha256": "0" * 64})
    _lines, release_ok = CHECK.run_status(release, None, gen)
    assert release_ok is False
