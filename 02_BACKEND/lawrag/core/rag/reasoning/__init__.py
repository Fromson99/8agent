"""Reasoning boundary: closure, proposition assessment and answer assembly."""

from lawrag.core.rag._boundary import load_owned, owned_modules

__all__ = sorted(owned_modules("reasoning"))


def __getattr__(name: str):
    return load_owned("reasoning", name)

