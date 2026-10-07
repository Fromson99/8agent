"""Knowledge boundary: reviewed rules, feedback ledgers and lifecycle controls."""

from lawrag.core.rag._boundary import load_owned, owned_modules

__all__ = sorted(owned_modules("knowledge"))


def __getattr__(name: str):
    return load_owned("knowledge", name)

