from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from lawrag.core.legal_graph import (
    COMPILER_CONTRACT_VERSION,
    SCHEMA_VERSION,
    canonical_json_text,
    content_sha256,
    stable_id,
)
from lawrag.core.rag import legal_graph_store


AUTHORITY = "a" * 64
PROJECTION_POLICY = "provision-card-v1.1"
FACET_FIELDS = (
    "definition_observation_ids",
    "frame_observation_ids",
    "requirement_observation_ids",
    "legacy_rule_assertion_ids",
    "relation_assertion_ids",
    "unresolved_relation_ids",
)


@dataclass
class Sidecar:
    root: Path
    generation_root: Path
    generation_id: str
    ids: dict[str, str]

    @property
    def index(self) -> Any:
        return SimpleNamespace(authority_generation=AUTHORITY)


@pytest.fixture(autouse=True)
def _isolated_store_cache() -> Any:
    legal_graph_store.reset_cache()
    yield
    legal_graph_store.reset_cache()


def _endpoint(
    ref_id: str,
    document_id: str,
    node_id: int,
    label: str,
    *,
    exact_span: bool = False,
) -> dict[str, Any]:
    selector: dict[str, Any] = {
        "document_id": document_id,
        "node_id": node_id,
        "coordinate": label,
    }
    precision = "EXACT_UNIT"
    if exact_span:
        quote = "대통령령"
        selector.update({
            "block_id": 0,
            "start": 0,
            "end": len(quote),
            "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        })
        precision = "EXACT_SPAN"
    return {
        "kind": "STRUCTURAL_UNIT",
        "precision": precision,
        "ref_id": ref_id,
        "selector": selector,
        "label": label,
    }


def _row(
    generation_id: str,
    row_type: str,
    row_id: str,
    layer: str,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_id": generation_id,
        "authority_generation": AUTHORITY,
        "layer": layer,
        "row_type": row_type,
        "id": row_id,
        **fields,
    }


def _write_gzip(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write((canonical_json_text(row) + "\n").encode("utf-8"))
    payload = path.read_bytes()
    packed = path.as_posix().split("/generations/", 1)
    relative = (
        packed[1].split("/", 1)[1] if len(packed) == 2 else path.name
    )
    return {
        "path": relative,
        "logical_path": relative.removesuffix(".gz"),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "rows": len(rows),
        "format": "jsonl",
        "compression": "gzip",
        "row_type": rows[0]["row_type"],
    }


def _card(
    generation_id: str,
    card_id: str,
    endpoint: dict[str, Any],
    member_id: str,
    *,
    assertion_ids: tuple[str, ...] = (),
    outgoing: tuple[str, ...] = (),
    incoming: tuple[str, ...] = (),
) -> dict[str, Any]:
    facets = {field: [] for field in FACET_FIELDS}
    facets["relation_assertion_ids"] = sorted(assertion_ids)
    return _row(
        generation_id,
        "provision_card",
        card_id,
        "projection",
        article_root=endpoint,
        article_root_id=member_id,
        structural_unit_id=member_id,
        facets=facets,
        relation_ports={
            "outgoing_projection_ids": sorted(outgoing),
            "incoming_projection_ids": sorted(incoming),
        },
        runtime_wired=False,
    )


def _build_sidecar(root: Path, *, unreachable_edge: bool = False) -> Sidecar:
    source_hashes = {"fixture": hashlib.sha256(b"fixture-source").hexdigest()}
    generation_digest = content_sha256({
        "schema_version": SCHEMA_VERSION,
        "compiler_contract": COMPILER_CONTRACT_VERSION,
        "projection_policy": PROJECTION_POLICY,
        "authority_generation": AUTHORITY,
        "source_hashes": source_hashes,
    })
    generation_id = f"lgv1-{generation_digest[:24]}"
    generation_root = root / "generations" / generation_id

    ids = {
        "law_root": stable_id("unit", "law-root"),
        "law_item": stable_id("unit", "law-item"),
        "decree_root": stable_id("unit", "decree-root"),
        "assertion": stable_id("relation", "delegation"),
        "closure": stable_id("closure", "delegation"),
        "law_card": stable_id("card", "law"),
        "decree_card": stable_id("card", "decree"),
        "old_source": stable_id("unit", "old-source"),
        "old_target": stable_id("unit", "old-target"),
        "old_assertion": stable_id("relation", "old-delegation"),
        "old_closure": stable_id("closure", "old-delegation"),
    }
    source = _endpoint(
        ids["law_item"], "law-doc", 2, "제2조제6호나목", exact_span=True
    )
    target = _endpoint(ids["decree_root"], "decree-doc", 10, "제4조")
    assertions = [_row(
        generation_id,
        "relation_assertion",
        ids["assertion"],
        "canonical",
        predicate="LEGISLATIVE_DELEGATION",
        family="LEGISLATIVE_LINK",
        source=source,
        target=target,
        claim_status="ACCEPTED",
        evidence_ids=[],
        resolution="EXACT_SOURCE_BACKED",
        review_state="SOURCE_BACKED",
        legacy_kind="DELEGATES_TO",
    )]
    closures = [_row(
        generation_id,
        "closure_projection",
        ids["closure"],
        "projection",
        relation_assertion_id=ids["assertion"],
        source_article_root_id=ids["law_root"],
        closure_mode="REQUIRED_WHEN_ACTIVATED",
        activation_policy="query_conditional_future_policy",
        runtime_wired=False,
    )]
    if unreachable_edge:
        assertions.append(_row(
            generation_id,
            "relation_assertion",
            ids["old_assertion"],
            "canonical",
            predicate="LEGISLATIVE_DELEGATION",
            family="LEGISLATIVE_LINK",
            source=_endpoint(ids["old_source"], "old-law", 20, "구법 제2조"),
            target=_endpoint(ids["old_target"], "old-decree", 30, "구 시행령"),
            claim_status="ACCEPTED",
            evidence_ids=[],
            resolution="EXACT_SOURCE_BACKED",
            review_state="SOURCE_BACKED",
            legacy_kind="DELEGATES_TO",
        ))
        closures.append(_row(
            generation_id,
            "closure_projection",
            ids["old_closure"],
            "projection",
            relation_assertion_id=ids["old_assertion"],
            closure_mode="REQUIRED_WHEN_ACTIVATED",
            activation_policy="query_conditional_future_policy",
            runtime_wired=False,
        ))

    cards = [
        _card(
            generation_id,
            ids["law_card"],
            _endpoint(ids["law_root"], "law-doc", 1, "제2조"),
            ids["law_root"],
            assertion_ids=(ids["assertion"],),
            outgoing=(ids["closure"],),
        ),
        _card(
            generation_id,
            ids["decree_card"],
            target,
            ids["decree_root"],
            assertion_ids=(ids["assertion"],),
            incoming=(ids["closure"],),
        ),
    ]
    row_sets = {
        "canonical/relation_assertions.jsonl.gz": assertions,
        "projections/closure_projections.jsonl.gz": closures,
        "projections/provision_cards.jsonl.gz": cards,
    }
    artifacts = {
        relative: _write_gzip(generation_root / relative, rows)
        for relative, rows in row_sets.items()
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": generation_id,
        "authority_generation": AUTHORITY,
        "authority_as_of": "20260828",
        "compiler_contract": COMPILER_CONTRACT_VERSION,
        "projection_policy": PROJECTION_POLICY,
        "runtime_wired": False,
        "source_hashes": source_hashes,
        "source_aggregate_sha256": content_sha256(source_hashes),
        "artifacts": artifacts,
        "counts": {"current_article_roots": len(cards)},
    }
    manifest["content_sha256"] = content_sha256(manifest)
    _write_manifest_and_pointer(root, manifest)

    validation = generation_root / "validation"
    validation.mkdir(parents=True)
    (validation / "summary.json").write_text(canonical_json_text({
        "schema_version": "legal-graph-validation-v1",
        "generation_id": generation_id,
        "ok": True,
        "error_count": 0,
    }), encoding="utf-8")
    return Sidecar(root, generation_root, generation_id, ids)


def _write_manifest_and_pointer(root: Path, manifest: dict[str, Any]) -> None:
    generation_id = str(manifest["generation_id"])
    generation_root = root / "generations" / generation_id
    generation_root.mkdir(parents=True, exist_ok=True)
    (generation_root / "manifest.json").write_text(
        canonical_json_text(manifest), encoding="utf-8"
    )
    pointer = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": generation_id,
        "authority_generation": manifest["authority_generation"],
        "projection_policy": manifest["projection_policy"],
        "manifest": f"generations/{generation_id}/manifest.json",
        "content_sha256": manifest["content_sha256"],
        "runtime_wired": manifest["runtime_wired"],
    }
    (root / "CURRENT.json").write_text(
        canonical_json_text(pointer), encoding="utf-8"
    )


def _mutate_manifest(sidecar: Sidecar, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = sidecar.generation_root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest.pop("content_sha256", None)
    manifest["content_sha256"] = content_sha256(manifest)
    _write_manifest_and_pointer(sidecar.root, manifest)


def _rewrite_artifact(
    sidecar: Sidecar,
    relative: str,
    mutate: Callable[[list[dict[str, Any]]], None],
) -> None:
    path = sidecar.generation_root / relative
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    mutate(rows)
    metadata = _write_gzip(path, rows)

    def update(manifest: dict[str, Any]) -> None:
        manifest["artifacts"][relative] = metadata

    _mutate_manifest(sidecar, update)


def _change_compiler_source(manifest: dict[str, Any]) -> None:
    manifest["source_hashes"]["fixture"] = "c" * 64
    manifest["source_aggregate_sha256"] = content_sha256(
        manifest["source_hashes"]
    )


def test_compiler_bound_snapshot_and_exact_span_are_retained(tmp_path: Path) -> None:
    sidecar = _build_sidecar(tmp_path, unreachable_edge=True)
    result = legal_graph_store.current_for(sidecar.index, root=tmp_path)

    assert result.status == "loaded" and result.snapshot is not None
    snapshot = result.snapshot
    assert snapshot.generation_id == sidecar.generation_id
    assert snapshot.loaded_rows == 6
    assert list(snapshot.edge_by_projection_id) == [sidecar.ids["closure"]]
    edge = snapshot.edge_by_projection_id[sidecar.ids["closure"]]
    assert (edge.source.block_id, edge.source.start, edge.source.end) == (0, 0, 4)
    assert edge.source.quote_sha256 == hashlib.sha256(
        "대통령령".encode("utf-8")
    ).hexdigest()
    assert snapshot.incident(("law-doc", 1)) == (edge,)
    assert snapshot.incident(("decree-doc", 10), direction="incoming") == (edge,)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda manifest: manifest.__setitem__(
                "compiler_contract", "legal-graph-compiler-v999"
            ),
            "unsupported compiler contract",
        ),
        (
            _change_compiler_source,
            "generation_id does not match compiler inputs",
        ),
        (
            lambda manifest: manifest["counts"].__setitem__(
                "current_article_roots", 999
            ),
            "manifest content_sha256 mismatch",
        ),
    ],
)
def test_manifest_compiler_generation_and_content_binding(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    reason: str,
) -> None:
    sidecar = _build_sidecar(tmp_path)
    manifest_path = sidecar.generation_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    if reason != "manifest content_sha256 mismatch":
        manifest.pop("content_sha256")
        manifest["content_sha256"] = content_sha256(manifest)
    _write_manifest_and_pointer(tmp_path, manifest)

    result = legal_graph_store.current_for(sidecar.index, root=tmp_path)

    assert result.status == "invalid" and result.snapshot is None
    assert reason in result.reasons[0]


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("invalid_row", "row schema invalid"),
        ("duplicate_id", "duplicate relation assertion id"),
        ("duplicate_port", "contains duplicate IDs"),
        ("metadata", "artifact metadata mismatch"),
    ],
)
def test_rows_metadata_duplicates_and_card_lists_fail_closed(
    tmp_path: Path, kind: str, reason: str
) -> None:
    sidecar = _build_sidecar(tmp_path)
    assertions_path = "canonical/relation_assertions.jsonl.gz"
    cards_path = "projections/provision_cards.jsonl.gz"
    if kind == "invalid_row":
        _rewrite_artifact(
            sidecar,
            assertions_path,
            lambda rows: rows[0].__setitem__("predicate", "NOT_A_PREDICATE"),
        )
    elif kind == "duplicate_id":
        _rewrite_artifact(sidecar, assertions_path, lambda rows: rows.append(rows[0]))
    elif kind == "duplicate_port":
        _rewrite_artifact(
            sidecar,
            cards_path,
            lambda rows: rows[0]["relation_ports"][
                "outgoing_projection_ids"
            ].append(sidecar.ids["closure"]),
        )
    else:
        _mutate_manifest(
            sidecar,
            lambda manifest: manifest["artifacts"][cards_path].__setitem__(
                "logical_path", "wrong.jsonl"
            ),
        )

    result = legal_graph_store.current_for(sidecar.index, root=tmp_path)

    assert result.status == "invalid" and result.snapshot is None
    assert reason in result.reasons[0]


class _SwapOnClose:
    def __init__(self, handle: Any, replacement: Path, target: Path) -> None:
        self._handle = handle
        self._replacement = replacement
        self._target = target
        self._closed = False

    def __enter__(self) -> "_SwapOnClose":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def read(self, size: int = -1) -> bytes:
        return self._handle.read(size)

    def close(self) -> None:
        if self._closed:
            return
        self._handle.close()
        os.replace(self._replacement, self._target)
        self._closed = True


def test_artifact_hash_and_parse_use_the_same_open_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _build_sidecar(tmp_path)
    relative = "canonical/relation_assertions.jsonl.gz"
    target = (sidecar.generation_root / relative).resolve()
    with gzip.open(target, "rt", encoding="utf-8") as handle:
        alternate_rows = [json.loads(line) for line in handle if line.strip()]
    alternate_rows[0]["predicate"] = "NOT_A_PREDICATE"
    replacement = tmp_path / "replacement.jsonl.gz"
    _write_gzip(replacement, alternate_rows)

    original_open = Path.open
    swapped = False

    def swapping_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        nonlocal swapped
        handle = original_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if path.resolve() == target and mode == "rb" and not swapped:
            swapped = True
            return _SwapOnClose(handle, replacement, target)
        return handle

    monkeypatch.setattr(Path, "open", swapping_open)
    result = legal_graph_store.current_for(sidecar.index, root=tmp_path)

    assert swapped is True
    assert result.status == "loaded" and result.snapshot is not None
    edge = result.snapshot.edge_by_projection_id[sidecar.ids["closure"]]
    assert edge.predicate == "LEGISLATIVE_DELEGATION"
    assert hashlib.sha256(target.read_bytes()).hexdigest() != json.loads(
        (sidecar.generation_root / "manifest.json").read_text(encoding="utf-8")
    )["artifacts"][relative]["sha256"]


def test_pointer_key_single_flight_and_negative_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _build_sidecar(tmp_path)
    real_load = legal_graph_store._load_snapshot
    entered = threading.Event()
    release = threading.Event()
    load_calls = 0

    def blocked_load(*args: Any, **kwargs: Any) -> Any:
        nonlocal load_calls
        load_calls += 1
        entered.set()
        assert release.wait(timeout=5)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(legal_graph_store, "_load_snapshot", blocked_load)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(legal_graph_store.current_for, sidecar.index, root=tmp_path)
            for _ in range(6)
        ]
        assert entered.wait(timeout=5)
        release.set()
        results = [future.result(timeout=5) for future in futures]

    assert load_calls == 1
    assert all(result.snapshot is results[0].snapshot for result in results)
    assert any("single_flight_wait" in result.reasons for result in results)

    legal_graph_store.reset_cache()
    failed_calls = 0

    def failed_load(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal failed_calls
        failed_calls += 1
        raise legal_graph_store.LegalGraphLoadError("broken fixture")

    monkeypatch.setattr(legal_graph_store, "_load_snapshot", failed_load)
    first = legal_graph_store.current_for(sidecar.index, root=tmp_path)
    second = legal_graph_store.current_for(sidecar.index, root=tmp_path)

    assert first.status == second.status == "invalid"
    assert failed_calls == 1
    assert "negative_cache_hit" in second.reasons


def test_reset_during_load_prevents_old_epoch_cache_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _build_sidecar(tmp_path)
    real_load = legal_graph_store._load_snapshot
    entered = threading.Event()
    release = threading.Event()
    load_calls = 0

    def first_load(*args: Any, **kwargs: Any) -> Any:
        nonlocal load_calls
        load_calls += 1
        entered.set()
        assert release.wait(timeout=5)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(legal_graph_store, "_load_snapshot", first_load)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            legal_graph_store.current_for, sidecar.index, root=tmp_path
        )
        assert entered.wait(timeout=5)
        legal_graph_store.reset_cache()
        release.set()
        assert future.result(timeout=5).status == "loaded"

    monkeypatch.setattr(legal_graph_store, "_load_snapshot", real_load)
    after_reset = legal_graph_store.current_for(sidecar.index, root=tmp_path)

    assert after_reset.status == "loaded"
    assert load_calls == 1
