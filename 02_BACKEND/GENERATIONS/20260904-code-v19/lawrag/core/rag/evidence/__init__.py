"""Evidence boundary: coordinates, relations, semantic stores and observations."""

from lawrag.core.rag._boundary import load_owned, owned_modules

__all__ = sorted(owned_modules("evidence"))


def __getattr__(name: str):
    return load_owned("evidence", name)

