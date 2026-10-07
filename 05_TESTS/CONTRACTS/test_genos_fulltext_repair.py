"""A published generation without fulltext can be repaired without changing its bytes."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.term_serving_bundle import verify_assets
from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from semantic_runtime.term_agent import TermAgent
from test_document_release import source

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "genos_fulltext_repair", ROOT / "06_TOOLS/COMMANDS/genos_fulltext_repair.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
repair = MODULE.main
E2E_SPEC = importlib.util.spec_from_file_location(
    "genos_generation_e2e", ROOT / "06_TOOLS/COMMANDS/genos_generation_e2e.py")
assert E2E_SPEC and E2E_SPEC.loader
E2E = importlib.util.module_from_spec(E2E_SPEC)
E2E_SPEC.loader.exec_module(E2E)


def test_repair_creates_new_bound_package(tmp_path: Path, term_glossary):
    original = source(tmp_path / "source.sqlite", [
        ("internal:v1", "가상내규", ["영업일에 관한 가상 규정 원문"]),
    ])
    built = tmp_path / "built"
    build_generation(original, term_glossary, built, serving=True)
    releases = tmp_path / "term-releases"
    published = releases / "old-run/unreviewed/generation"
    published.parent.mkdir(parents=True)
    shutil.copytree(built / "generation", published)
    shutil.rmtree(published / "fulltext")
    old_manifest = json.loads((published / "manifest.json").read_text())
    old_manifest.pop("fulltext")
    (published / "manifest.json").write_text(json.dumps(old_manifest), encoding="utf-8")
    old_hash = sha(published / "manifest.json")
    assert verify_assets(published)["verified"]

    assert repair(["--source-generation", str(published), "--output-root", str(releases),
                   "--package-name", "repaired", "--workers", "1",
                   "--scratch-root", str(tmp_path)]) == 0
    repaired = releases / "repaired/generation"
    assert sha(published / "manifest.json") == old_hash
    assert not (published / "fulltext").exists()
    assert verify_assets(repaired)["verified"]
    manifest = json.loads((repaired / "manifest.json").read_text())
    receipt = json.loads((releases / "repaired/share-receipt.json").read_text())
    assert receipt["manifest_sha256"] == sha(repaired / "manifest.json")
    assert receipt["files"]["fulltext/manifest.json"] == sha(repaired / "fulltext/manifest.json")
    assert E2E.audit(ROOT, repaired)["status"] == "PASS"
    with closing(Store(repaired)) as store:
        pipeline = SimpleNamespace(store=store, contracts=SimpleNamespace(root=tmp_path))
        agent = TermAgent(pipeline, {"fulltext": {"path": "fulltext",
                          "navigation_index_sha256": "0" * 64, "manifest_sha256": "0" * 64}})
        assert agent.get_fulltext().manifest["navigation_index_sha256"] == (
            agent.get_index().manifest["index_sha256"])
