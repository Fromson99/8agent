import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "00_SYSTEM/INTERNAL_LAYOUT.json"
UPPER_CONTAINER = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _policy() -> dict:
    return json.loads(POLICY.read_text("utf-8"))


def test_managed_containers_are_complete_and_uppercase() -> None:
    policy = _policy()
    for relative, expected in policy["managed_containers"].items():
        parent = ROOT / relative
        actual = sorted(
            path.name for path in parent.iterdir()
            if path.is_dir() and path.name != "__pycache__"
        )
        assert actual == sorted(expected), (relative, actual, expected)
        assert all(UPPER_CONTAINER.fullmatch(name) for name in actual)


def test_language_native_and_receipt_bound_containers_are_explicit() -> None:
    policy = _policy()
    for relative, expected in policy["mixed_containers"].items():
        parent = ROOT / relative
        actual = sorted(path.name for path in parent.iterdir() if path.is_dir())
        assert actual == sorted(expected), (relative, actual, expected)


def test_retired_mutable_names_do_not_exist() -> None:
    for relative in _policy()["retired_mutable_names"]:
        assert not (ROOT / relative).exists(), relative


def test_reference_documents_are_categorized() -> None:
    reference = ROOT / "07_DOCS/REFERENCE"
    loose_files = [path.name for path in reference.iterdir() if path.is_file()]
    assert loose_files == ["README.md"]


def test_no_editor_backup_files_in_managed_mutable_roots() -> None:
    roots = [ROOT / value for value in ("03_FRONTEND", "05_TESTS", "06_TOOLS", "07_DOCS", "09_ARTIFACTS")]
    offenders = []
    for managed in roots:
        for path in managed.rglob("*"):
            if "GENERATIONS" in path.parts:
                continue
            if path.name.startswith("~$") or path.suffix == ".orig":
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
