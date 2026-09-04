"""Legacy research profile adapter registry.

The bodies are kept at their historical paths so completed ADR imports remain
reproducible.  New candidates must use ``scripts/adr_candidate.py snapshot``
and live below ``lawrag/research/candidates``.
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType


_LEGACY = {
    "legacy": "lawrag.core.rag.integrated_legal_research",
    "coverage-preserving-v1": "lawrag.core.rag.coverage_preserving_research",
    "scope-entailment-bundle-v2": "lawrag.core.rag.scope_entailment_bundle_research",
    "issue-role-atomic-entailment-v3": (
        "lawrag.core.rag.issue_role_atomic_entailment_research"
    ),
}


def load(profile_id: str) -> ModuleType:
    module_name = _LEGACY.get(profile_id)
    if module_name is None:
        raise ValueError(f"unknown research profile: {profile_id}")
    module = import_module(module_name)
    for name in ("extend_sections", "fallback_to_floor"):
        if not callable(getattr(module, name, None)):
            raise ValueError(f"research profile contract missing {name}: {module_name}")
    return module


def specs() -> list[dict[str, str]]:
    return [
        {"profile_id": key, "module": value, "status": "legacy-reproducibility"}
        for key, value in sorted(_LEGACY.items())
    ]
