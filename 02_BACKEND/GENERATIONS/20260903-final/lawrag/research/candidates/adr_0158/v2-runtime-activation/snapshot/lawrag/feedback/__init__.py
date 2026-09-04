"""Feedback control-plane contracts; no feedback mutates canonical data directly."""

from .shortcuts import (
    QuerySignature,
    Shortcut,
    ShortcutContractError,
    ShortcutResolutionContext,
    build_signature,
    load_shortcuts,
    select_shortcut,
    shortcut_from_mapping,
)

__all__ = [
    "QuerySignature",
    "Shortcut",
    "ShortcutContractError",
    "ShortcutResolutionContext",
    "build_signature",
    "load_shortcuts",
    "select_shortcut",
    "shortcut_from_mapping",
]
