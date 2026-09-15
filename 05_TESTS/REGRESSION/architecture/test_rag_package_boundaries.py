from pathlib import Path

from lawrag.core.rag._boundary import MODULE_OWNERS


ROOT = Path(__file__).resolve().parents[3]


def test_every_compatibility_module_has_exactly_one_owner() -> None:
    rag = ROOT / "02_BACKEND/lawrag/core/rag"
    actual = {
        path.stem
        for path in rag.glob("*.py")
        if path.name not in {"__init__.py", "_boundary.py"}
    }
    declared = [name for names in MODULE_OWNERS.values() for name in names]
    assert len(declared) == len(set(declared))
    assert set(declared) == actual
    assert "experiments" not in actual


def test_new_boundary_facades_are_lazy_and_complete() -> None:
    from lawrag.core.rag import evidence, knowledge, reasoning, retrieval

    assert retrieval.index.__name__ == "lawrag.core.rag.index"
    assert evidence.legal_evidence.__name__ == "lawrag.core.rag.legal_evidence"
    assert reasoning.legalclosure.__name__ == "lawrag.core.rag.legalclosure"
    assert knowledge.rules.__name__ == "lawrag.core.rag.rules"
