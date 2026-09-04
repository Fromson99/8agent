from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM/WORKSPACE.json").is_file()
)
SPEC = importlib.util.spec_from_file_location(
    "publish_code_generation", ROOT / "06_TOOLS/publish_code_generation.py"
)
assert SPEC and SPEC.loader
PUBLISHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISHER)


def test_code_generation_excludes_research_corpus_and_local_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "core").mkdir(parents=True)
    (source / "core/runtime.py").write_text("VALUE = 1\n", "utf-8")
    (source / "research/candidates").mkdir(parents=True)
    (source / "research/candidates/frozen.py").write_text("frozen\n", "utf-8")
    (source / "agents/agent6/corpus/raw").mkdir(parents=True)
    (source / "agents/agent6/corpus/raw/source.pdf").write_bytes(b"raw")
    (source / "local.py.orig").write_text("backup\n", "utf-8")

    target = tmp_path / "target"
    PUBLISHER._copy_source(source, target)

    assert (target / "core/runtime.py").is_file()
    assert not (target / "research").exists()
    assert not (target / "agents/agent6/corpus").exists()
    assert not (target / "local.py.orig").exists()
