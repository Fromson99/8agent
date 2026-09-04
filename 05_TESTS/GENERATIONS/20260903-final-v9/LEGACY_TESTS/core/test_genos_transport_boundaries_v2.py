from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CODE_SHIP = _module("code_ship_contract_v2", "scripts/code_ship.py")
PATCH_SENDER = _module("push_patch_contract_v2", "scripts/push_patch_mail.py")
PATCH_RECEIVER = _module("genos_patch_contract_v2", "scripts/genos_patch_apply.py")


def test_code_bundle_contains_the_workspace_contract_but_not_data_roots():
    paths = {
        CODE_SHIP._bundle_relative(path)
        for path in CODE_SHIP._files()
    }

    assert "00_SYSTEM/WORKSPACE.json" in paths
    assert "00_SYSTEM/SCHEMAS/dataset-package-v2.schema.json" in paths
    assert not any(path.startswith("lawrag/research/") for path in paths)
    assert not any(
        path.startswith((
            "01_DATA/",
            "04_EXPERIMENTS/",
            "09_ARTIFACTS/",
            "90_RUNTIME/",
            "99_ARCHIVE/",
        ))
        for path in paths
    )


@pytest.mark.parametrize(
    "path",
    [
        "01_DATA/PACKAGES/INTERNAL/secret.jsonl",
        "04_EXPERIMENTS/EXPERIMENTS/ADR-9999/run.json",
        "09_ARTIFACTS/report.json",
        "90_RUNTIME/logs/service.log",
        "99_ARCHIVE/legacy.json",
    ],
)
def test_incremental_patch_rejects_canonical_data_and_runtime_roots(path: str):
    assert PATCH_SENDER._blocked(path) is not None
    with pytest.raises(ValueError, match="패치 금지 경로"):
        PATCH_RECEIVER._safe_rel(path)


def test_incremental_patch_keeps_system_and_future_code_roots_available():
    for path in (
        "00_SYSTEM/WORKSPACE.json",
        "02_BACKEND/lawrag/api.py",
        "03_FRONTEND/app.tsx",
        "06_TOOLS/audit.py",
        "07_DOCS/runbook.md",
        "08_DEPLOYMENT/GENOS/profile.json",
    ):
        assert PATCH_SENDER._blocked(path) is None
        assert PATCH_RECEIVER._safe_rel(path) == path


def test_minimal_verified_code_bundle_can_bootstrap_workspace_after_extract(tmp_path):
    relative_paths = [
        "service.py",
        "requirements-serving.txt",
        "00_SYSTEM/WORKSPACE.json",
        "lawrag/__init__.py",
        "lawrag/datasets/__init__.py",
        "lawrag/datasets/catalog.py",
        "lawrag/datasets/sync.py",
        "lawrag/platform/__init__.py",
        "lawrag/platform/paths.py",
        "lawrag/platform/release.py",
        "lawrag/platform/workspace.py",
        "lawrag/runtime/__init__.py",
        "lawrag/runtime/registry.py",
    ]
    paths = [ROOT / relative for relative in relative_paths]
    assert all(path.is_file() for path in paths)
    rows, payloads = CODE_SHIP._rows(paths)
    bundle = tmp_path / "minimal-code.zip"
    manifest = {"format": "8agent-code/1", "files": rows}
    with zipfile.ZipFile(bundle, "w") as archive:
        for relative, raw in payloads.items():
            archive.writestr(relative, raw)
        archive.writestr(CODE_SHIP.MANIFEST, json.dumps(manifest))

    CODE_SHIP.verify(bundle)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from lawrag.datasets.sync import ROOT; "
                "from lawrag.platform import load_layout; "
                "assert ROOT == load_layout().root; print(load_layout().mode)"
            ),
        ],
        cwd=extracted,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "v2-only"
