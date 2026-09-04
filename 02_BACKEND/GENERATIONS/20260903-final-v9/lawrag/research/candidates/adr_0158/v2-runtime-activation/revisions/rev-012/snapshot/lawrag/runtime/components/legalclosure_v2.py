"""Stable production adapter for LegalClosure v2."""
from __future__ import annotations

from lawrag.core.rag import legalclosure_runtime


def retrieve(*args, **kwargs):
    # Research profiles are never accepted through a product endpoint.  A
    # promoted implementation must be copied into this package as a reviewed
    # production component and selected by its registered profile ID.
    kwargs.pop("research_profile", None)
    kwargs["integrated_research_enabled"] = False
    return legalclosure_runtime.retrieve(*args, **kwargs)
