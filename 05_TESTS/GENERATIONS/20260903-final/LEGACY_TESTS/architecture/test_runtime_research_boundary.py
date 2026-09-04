from __future__ import annotations

import ast
from pathlib import Path

import pytest

from lawrag.runtime import registry


ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_production_runtime_does_not_import_research_package() -> None:
    for path in (ROOT / "lawrag" / "runtime").rglob("*.py"):
        assert not any(
            name == "lawrag.research" or name.startswith("lawrag.research.")
            for name in _imports(path)
        ), path


def test_registry_accepts_only_production_component_modules() -> None:
    assert registry.specs()
    for spec in registry.specs():
        assert spec["module"].startswith(registry.PRODUCTION_PREFIX)
        registry.validate_profile_id(spec["profile_id"])
    with pytest.raises(ValueError, match="unregistered production"):
        registry.validate_profile_id("adr-0118-research-candidate")
def test_core_runtime_requires_explicit_research_injection(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace
    from lawrag.core.rag import legalclosure_runtime

    registry_path = tmp_path / "canonical.json"
    registry_path.write_text("{}", "utf-8")
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "registry_path", lambda: registry_path)
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "load_registry", lambda _path: {})
    monkeypatch.setattr(
        legalclosure_runtime.legalclosure,
        "retrieve",
        lambda *args, **kwargs: ([], {"assertion": {}}),
    )
    with pytest.raises(ValueError, match="explicitly injected research_profile"):
        legalclosure_runtime.retrieve(
            SimpleNamespace(), "질문", llm=None, integrated_research_enabled=True
        )
