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
from .lifecycle import (
    FeedbackLifecycleError,
    build_data_correction_event,
    build_data_error_event,
    build_rag_feedback_event,
    compile_change_candidates,
    validate_change_candidate,
    validate_feedback_event,
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
    "FeedbackLifecycleError",
    "build_data_correction_event",
    "build_data_error_event",
    "build_rag_feedback_event",
    "compile_change_candidates",
    "validate_change_candidate",
    "validate_feedback_event",
]
