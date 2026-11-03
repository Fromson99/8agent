"""Read-only access to data paths sealed by an active release.

Offline tools must use this module instead of reconstructing paths below
``01_DATA``.  The release store validates the active pointer, manifest,
activation ledger, validation receipts, and runtime binding before a path is
returned.
"""

from __future__ import annotations

from pathlib import Path

from .release import ReleaseStore


def active_runtime_paths(
    workspace: str | Path, *, target: str = "local"
) -> dict[str, Path]:
    root = Path(workspace).expanduser().resolve()
    store = ReleaseStore(
        root / "01_DATA" / "ACTIVE" / target,
        target=target,
        read_only=True,
    )
    pointer = store.load_active()
    if pointer is None:
        raise RuntimeError(f"no active {target} release")
    release = store.load_manifest(pointer.release_id)
    # Offline inspection does not execute the deployed code package.  The
    # pointer, activation ledger, manifest and binding hashes are still
    # validated; service startup performs the stronger code-package readiness
    # check before serving requests.
    binding = store.load_runtime_binding(release.release_id, verify_paths=False)
    runtime_root = store.root / "RUNTIMES" / release.manifest_sha256
    return {
        key: Path(value)
        for key, value in binding.resolved_paths(runtime_root).items()
    }


def active_structure_path(
    workspace: str | Path, *, target: str = "local"
) -> Path:
    return active_runtime_paths(workspace, target=target)["STRUCTURE_STORE"]
