"""Logical workspace paths shared by legacy and v2 package locations."""

from __future__ import annotations

from pathlib import Path

from .workspace import load_layout


_V2_RUNTIME_BUCKETS = frozenset({"cache", "logs", "mounts", "out", "private", "tmp"})


def repository_root() -> Path:
    return load_layout().root


def root_path(root_id: str, *parts: str) -> Path:
    return load_layout().path(root_id).joinpath(*parts)


def persisted_data_path(value: str | Path) -> Path:
    """Resolve a persisted data-relative manifest path through the active root.

    Manifests intentionally keep stable values such as ``data/corpus/...``.
    Under v2 those values must resolve below ``01_DATA`` without rewriting the
    immutable source manifest.  Other workspace roots intentionally are not
    handled here: their content projections are not yet uniform or activated.
    """

    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"data path must be a safe relative path: {value!r}")
    if relative.parts[0] not in {"data", "01_DATA"}:
        raise ValueError(f"persisted path is outside the data root: {value!r}")
    return data_path(*relative.parts[1:])


def manifest_asset_path(manifest: str | Path, value: str | Path) -> Path:
    """Resolve a file reference stored inside a collection manifest.

    Collection manifests carry two path conventions and both must keep working.
    The RAW layer writes them relative to the manifest itself
    (``표준투자권유준칙/별표서식/0000_[참고 1].hwp``), while the older corpus
    layout wrote them from the data root (``data/corpus/law/...``).  Callers see
    one resolver so a layout move cannot silently disconnect annex sidecars from
    the body that cites them.
    """

    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"manifest asset must be a safe relative path: {value!r}")
    if relative.parts[0] in {"data", "01_DATA"}:
        return data_path(*relative.parts[1:])
    return Path(manifest).resolve().parent / relative


def data_path(*parts: str) -> Path:
    return root_path("data", *parts)


def runtime_path(*parts: str) -> Path:
    layout = load_layout()
    base = layout.path("runtime")
    if (
        base.name == "90_RUNTIME"
        and parts
        and parts[0].casefold() in _V2_RUNTIME_BUCKETS
    ):
        parts = (parts[0].upper(), *parts[1:])
    elif base.name == "90_RUNTIME" and parts and parts[0].casefold() == "eval":
        parts = ("OUT", "eval", *parts[1:])
    return base.joinpath(*parts)
