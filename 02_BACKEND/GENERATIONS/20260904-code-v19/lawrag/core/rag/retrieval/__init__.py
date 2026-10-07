"""Retrieval boundary: candidate discovery, indexing, expansion and selection."""

from lawrag.core.rag._boundary import load_owned, owned_modules

__all__ = sorted(owned_modules("retrieval"))


def __getattr__(name: str):
    return load_owned("retrieval", name)

