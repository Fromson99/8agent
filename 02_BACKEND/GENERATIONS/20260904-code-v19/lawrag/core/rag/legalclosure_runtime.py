"""LegalClosure 운영 의존성 조립 경계.

검색 알고리즘은 ``legalclosure``에 남기고 canonical registry, fingerprint와 승인
shortcut 저장소 로드는 여기서 한 번만 조립한다.
"""

from __future__ import annotations

import time
from collections import Counter
from copy import deepcopy
from typing import Any, Mapping, Sequence

from lawrag.core.rag import (
    article_reachability,
    conceptfirst,
    legal_graph_closure,
    legal_semantic_search,
    legalclosure,
)
from lawrag.platform import main_promotion
from lawrag.core.rag.answer import Section
from lawrag.runtime.content_snapshot import (
    ContentSnapshotError,
    current_content_snapshot,
)
from lawrag.runtime import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.assertion_shortcuts import (
    ShortcutIndex,
    ShortcutLoadResult,
    canonical_fingerprint,
    load_runtime,
)
from lawrag.core.rag.index import Index


def retrieve(index: Index, question: str, *, llm, assertion_llm=None,
             cap: int = 20, shortcut_enabled: bool = False,
             feedback_enabled: bool = False, graph_enabled: bool = False,
             semantic_graph_enabled: bool = False,
             graph_root=None, reachability_trace=None,
             integrated_research_enabled: bool = False,
             integrated_cap: int = 32,
             integrated_profile: str = "legacy",
             research_profile=None,
             baseline_result=None):
    content_snapshot = current_content_snapshot()
    index_snapshot = getattr(index, "content_snapshot", None)
    if content_snapshot is not None:
        if index_snapshot is None:
            raise ContentSnapshotError(
                "retrieval index is not bound to the process content snapshot"
            )
        if (
            index_snapshot.content_snapshot_sha256
            != content_snapshot.content_snapshot_sha256
        ):
            raise ContentSnapshotError(
                "retrieval index belongs to another content snapshot"
            )
        main_state = main_promotion.load_state()
        if (
            main_state.get("generation") != content_snapshot.main_generation
            or main_promotion.fingerprint(main_state)
            != content_snapshot.main_state_sha256
        ):
            raise ContentSnapshotError(
                "active MAIN state disagrees with the pinned release"
            )
    registry_path = conceptfirst.registry_path()
    if content_snapshot is not None and not registry_path.is_file():
        raise ContentSnapshotError(
            "release semantic bundle has no domain_graph/canonical.json"
        )
    registry = conceptfirst.load_registry(registry_path)
    if shortcut_enabled and content_snapshot is None:
        shortcut = load_runtime(
            corpus_fingerprint=canonical_fingerprint(registry_path))
    else:
        shortcut = ShortcutLoadResult(
            ShortcutIndex([]),
            "disabled",
            "",
            reasons=((
                "unbound_shortcut_disabled_for_sourceset"
                if content_snapshot is not None and shortcut_enabled
                else "feature_switch_off"
            ),),
        )
    if integrated_research_enabled and baseline_result is not None:
        try:
            baseline_sections, baseline_meta = baseline_result
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "baseline_result must be the (sections, meta) tuple"
            ) from exc
        sections = deepcopy(list(baseline_sections))
        meta = deepcopy(dict(baseline_meta))
        meta["baseline_result_shared"] = True
    else:
        sections, meta = legalclosure.retrieve(
            index, question, registry, llm=llm, assertion_llm=assertion_llm,
            cap=cap, shortcut_index=shortcut.index,
            feedback_enabled=feedback_enabled,
            reachability_trace=reachability_trace)
        meta["baseline_result_shared"] = False
    if semantic_graph_enabled or graph_enabled:
        floor = list(sections)
        if semantic_graph_enabled:
            sections, graph_meta = legal_semantic_search.extend_sections(
                index, question, sections, cap=cap, root=graph_root)
        else:
            sections, graph_meta = legal_graph_closure.extend_sections(
                index, question, sections, cap=cap, root=graph_root)
        floor_coordinates = [(section.doc_id, section.node) for section in floor]
        final_coordinates = [(section.doc_id, section.node) for section in sections]
        changed = final_coordinates != floor_coordinates
        if changed:
            capture = meta.get("article_reachability")
            if capture is not None:
                trace_started = time.perf_counter()
                try:
                    if semantic_graph_enabled:
                        meta["article_reachability"] = _merge_semantic_reachability(
                            index, capture, sections, graph_meta
                        )
                    else:
                        meta["article_reachability"] = _merge_graph_reachability(
                            index, capture, sections, graph_meta
                        )
                    graph_meta["reachability"] = {
                        "status": "merged",
                        "final_count": len(sections),
                    }
                    meta["article_reachability_elapsed_ms"] = round(
                        float(meta.get("article_reachability_elapsed_ms") or 0.0)
                        + (time.perf_counter() - trace_started) * 1000,
                        3,
                    )
                except Exception as exc:
                    sections = floor
                    final_coordinates = floor_coordinates
                    changed = False
                    for number, section in enumerate(sections, 1):
                        section.n = number
                    graph_meta = legal_graph_closure.rollback_to_floor(
                        graph_meta,
                        len(floor),
                        f"article_reachability:{type(exc).__name__}:{exc}",
                    )
            else:
                graph_meta["reachability"] = {
                    "status": "not_recorded",
                    "final_count": len(sections),
                }
        if changed:
            selected = meta.setdefault("selected", [])
            if semantic_graph_enabled:
                final_set = set(final_coordinates)
                selected[:] = [
                    row for row in selected
                    if (row.get("doc_id"), row.get("node")) in final_set
                ]
            known = {(row.get("doc_id"), row.get("node")) for row in selected}
            annotations = meta.setdefault("legal_annotations", {})
            annotation_rows = annotations.setdefault("rows", [])
            annotation_known = {
                (row.get("doc_id"), row.get("node")) for row in annotation_rows
            }
            graph_coordinates = {
                (row.get("doc_id"), row.get("node"))
                for row in graph_meta.get("added") or ()
            }
            for section in sections:
                coordinate = (section.doc_id, section.node)
                if coordinate not in graph_coordinates:
                    continue
                if coordinate not in known:
                    selected.append({
                        "doc_id": section.doc_id,
                        "node": section.node,
                        "doc": section.doc,
                        "path": section.path,
                        "origin": (
                            "legal-semantic-v2" if semantic_graph_enabled
                            else "legal-graph-v1"
                        ),
                    })
                    known.add(coordinate)
                if section.legal_meta and coordinate not in annotation_known:
                    annotation_rows.append(section.legal_meta)
                    annotation_known.add(coordinate)
            suffix = (
                "+typed-semantic-legal-graph"
                if semantic_graph_enabled else "+conditional-legal-graph"
            )
            meta["strategy"] = f"{meta.get('strategy') or 'legalclosure'}{suffix}"
        if semantic_graph_enabled and graph_meta.get("legal_assessments"):
            meta["legal_assessments"] = list(
                graph_meta.get("legal_assessments") or ()
            )
    else:
        graph_meta = legal_graph_closure.disabled_meta(len(sections))
    meta["legal_graph"] = graph_meta

    if integrated_research_enabled:
        if research_profile is None:
            raise ValueError(
                "research execution requires an explicitly injected research_profile; "
                "production runtime never resolves ADR candidates"
            )
        for required in ("extend_sections", "fallback_to_floor"):
            if not callable(getattr(research_profile, required, None)):
                raise ValueError(
                    f"research_profile contract missing callable: {required}"
                )
        floor = list(sections)
        case_id = str(getattr(reachability_trace, "case_id", "") or "runtime-case")
        arm_id = str(
            getattr(reachability_trace, "arm_id", "")
            or "integrated-seven-layer"
        )
        try:
            sections, integrated_meta = research_profile.extend_sections(
                index,
                question,
                floor,
                llm=llm,
                cap=integrated_cap,
                graph_root=graph_root,
                case_id=case_id,
                arm_id=arm_id,
            )
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"[:500]
            sections, integrated_meta = research_profile.fallback_to_floor(
                index,
                floor,
                case_id=case_id,
                arm_id=arm_id,
                reason=reason,
            )
        if integrated_meta.get("added_count"):
            known = {
                (row.get("doc_id"), row.get("node"))
                for row in meta.setdefault("selected", [])
            }
            for section in sections:
                coordinate = (section.doc_id, section.node)
                if coordinate in known:
                    continue
                meta["selected"].append({
                    "doc_id": section.doc_id,
                    "node": section.node,
                    "doc": section.doc,
                    "path": section.path,
                    "origin": "integrated-legal-research-v1",
                })
                known.add(coordinate)
            meta["strategy"] = (
                f"{meta.get('strategy') or 'legalclosure'}"
                "+integrated-legal-research-v1"
            )
    else:
        integrated_meta = {
            "enabled": False,
            "status": "disabled",
            "before_count": len(sections),
            "after_count": len(sections),
            "added_count": 0,
            "baseline_floor_preserved": True,
            "direct_conclusion_allowed": False,
        }
    meta["integrated_research"] = integrated_meta
    assertion_meta = meta.setdefault("assertion", {})
    assertion_meta.setdefault("shortcut", {"used": False})
    assertion_meta["shortcut"]["store"] = shortcut.as_dict()
    meta["runtime"] = {
        "registry_path": str(registry_path),
        "shortcut_status": shortcut.status,
        "legal_graph_status": graph_meta.get("status"),
        "integrated_research_status": integrated_meta.get("status"),
        "integrated_research_profile": integrated_profile,
        "main_pipeline": main_promotion.runtime_provenance(),
    }
    if content_snapshot is not None:
        receipt = content_snapshot.compact_receipt()
        meta["content_snapshot"] = receipt
        meta["runtime"]["content_snapshot"] = receipt
    # Runtime extensions append graph/research selection and annotation rows
    # after the base retriever has enriched its own audit.  Run the same
    # deterministic pass once more so every late coordinate carries the exact
    # SourceSet artifact proof.  In legacy mode the helper is a no-op.
    legalclosure.enrich_content_provenance(index, meta)
    return sections, meta


def _merge_semantic_reachability(
    index: Index,
    capture: Mapping[str, Any],
    sections: Sequence[Section],
    semantic_meta: Mapping[str, Any],
) -> dict[str, Any]:
    """Replace the terminal presentation with measured semantic search stages."""
    article_reachability.validate_capture(capture)
    old_ledger = capture.get("stage_ledger")
    if not isinstance(old_ledger, Mapping):
        raise ValueError("article reachability stage_ledger is missing")
    old_stages = list(old_ledger.get("stages") or ())
    if not old_stages or old_stages[-1].get("stage_id") != "present":
        raise ValueError("article reachability terminal stage must be present")

    canonicalize = stage_ledger.index_article_root_canonicalizer(index)
    recorder = stage_ledger.StageLedgerRecorder(
        str(old_ledger.get("case_id") or capture.get("case_id") or ""),
        str(old_ledger.get("arm_id") or capture.get("arm_id") or ""),
        canonicalize,
    )
    for row in old_stages[:-1]:
        _replay_stage(recorder, row)
    _replay_stage(recorder, old_stages[-1], stage_id="pre-legal-semantic-present")

    stages = semantic_meta.get("stages") or {}
    union_coordinates = [tuple(value) for value in stages.get("candidate-union") or ()]
    closure_coordinates = [tuple(value) for value in stages.get("typed-closure") or ()]
    final_coordinates = [(section.doc_id, section.node) for section in sections]
    recorder.record_stage(
        "legal-semantic-landing-union",
        "retrieve",
        union_coordinates,
        parent_stage_ids=("pre-legal-semantic-present",),
    )
    recorder.record_stage(
        "legal-semantic-typed-closure",
        "expand",
        closure_coordinates,
        parent_stage_ids=("legal-semantic-landing-union",),
    )
    final_set = {canonicalize(value) for value in final_coordinates}
    closure_set = {canonicalize(value) for value in closure_coordinates}
    explicit_reasons = {
        canonicalize(tuple(row["coordinate"])): str(row["reason"])
        for row in semantic_meta.get("discarded_floor") or ()
    }
    discard_reasons = [
        (
            coordinate,
            explicit_reasons.get(
                coordinate, "not_selected_by_bounded_semantic_bundle_rerank",
            ),
        )
        for coordinate in sorted(closure_set - final_set)
    ]
    recorder.record_stage(
        "legal-semantic-bundle-rerank",
        "rerank",
        final_coordinates,
        parent_stage_ids=("legal-semantic-typed-closure",),
        discard_reasons=discard_reasons,
    )
    recorder.record_stage(
        "present",
        "present",
        final_coordinates,
        parent_stage_ids=("legal-semantic-bundle-rerank",),
    )
    new_ledger = recorder.capture()

    events = deepcopy(list(capture.get("events") or ()))
    original_final = {
        canonicalize((row["doc_id"], row["node"]))
        for row in old_stages[-1].get("after") or ()
    }
    for rank, section in enumerate(sections, 1):
        coordinate = canonicalize((section.doc_id, section.node))
        if coordinate in original_final:
            continue
        identity = {"doc_id": coordinate[0], "node": coordinate[1]}
        events.append({
            "event_no": len(events) + 1,
            "channel": "PRESENT",
            "task": "legal-semantic-presentation",
            "decision": "selected",
            "reason_code": "selected_semantic_bundle",
            "raw_coordinate": deepcopy(identity),
            "article_coordinate": deepcopy(identity),
            "source_coordinate": None,
            "trigger_type": "semantic_card_or_typed_closure",
            "trigger_value": [],
            "rank": rank,
            "score": None,
            "mandatory": True,
            "detail": {
                "origin": "legal-semantic-v2",
                "generation_id": semantic_meta.get("generation_id") or "",
            },
        })

    value = {
        key: deepcopy(item)
        for key, item in capture.items()
        if key not in {"capture_sha256", "stage_ledger", "events", "event_reason_counts"}
    }
    value["stage_ledger"] = new_ledger
    value["events"] = events
    value["event_reason_counts"] = dict(sorted(Counter(
        row["reason_code"] for row in events
    ).items()))
    value["capture_sha256"] = stage_ledger.deterministic_sha256(value)
    article_reachability.validate_capture(value)
    return value


def _merge_graph_reachability(
    index: Index,
    capture: Mapping[str, Any],
    sections: Sequence[Section],
    graph_meta: Mapping[str, Any],
) -> dict[str, Any]:
    """Replace the baseline terminal stage with graph-expand -> final present."""
    article_reachability.validate_capture(capture)
    old_ledger = capture.get("stage_ledger")
    if not isinstance(old_ledger, Mapping):
        raise ValueError("article reachability stage_ledger is missing")
    old_stages = list(old_ledger.get("stages") or ())
    if not old_stages or old_stages[-1].get("stage_id") != "present":
        raise ValueError("article reachability terminal stage must be present")
    old_present = old_stages[-1]
    baseline_present_stage_id = "pre-legal-graph-present"
    graph_stage_id = "legal-graph-closure-expand"
    reserved_stage_ids = {baseline_present_stage_id, graph_stage_id}
    if any(
        row.get("stage_id") in reserved_stage_ids for row in old_stages[:-1]
    ):
        raise ValueError("article reachability graph stage already exists")

    canonicalize = stage_ledger.index_article_root_canonicalizer(index)
    recorder = stage_ledger.StageLedgerRecorder(
        str(old_ledger.get("case_id") or capture.get("case_id") or ""),
        str(old_ledger.get("arm_id") or capture.get("arm_id") or ""),
        canonicalize,
    )
    for row in old_stages[:-1]:
        _replay_stage(recorder, row)
    _replay_stage(recorder, old_present, stage_id=baseline_present_stage_id)

    final_coordinates = [(section.doc_id, section.node) for section in sections]
    old_occurrences = old_present.get("occurrence_counts") or {}
    recorder.record_stage(
        graph_stage_id,
        "expand",
        final_coordinates,
        parent_stage_ids=(baseline_present_stage_id,),
        before_occurrence_count=int(old_occurrences.get("after") or 0),
        after_occurrence_count=len(final_coordinates),
    )
    recorder.record_stage(
        "present",
        "present",
        final_coordinates,
        parent_stage_ids=(graph_stage_id,),
        before_occurrence_count=len(final_coordinates),
        after_occurrence_count=len(final_coordinates),
    )
    new_ledger = recorder.capture()

    events = deepcopy(list(capture.get("events") or ()))
    selected_by_coordinate = {
        (row.get("doc_id"), row.get("node")): row
        for row in graph_meta.get("selected") or ()
    }
    added_coordinates = {
        (row.get("doc_id"), row.get("node"))
        for row in graph_meta.get("added") or ()
    }
    for rank, section in enumerate(sections, 1):
        coordinate = (section.doc_id, section.node)
        if coordinate not in added_coordinates:
            continue
        provenance = selected_by_coordinate.get(coordinate) or {}
        source = None
        if provenance.get("source_doc_id") and isinstance(
            provenance.get("source_node"), int
        ):
            source = {
                "doc_id": provenance["source_doc_id"],
                "node": provenance["source_node"],
            }
        identity = {"doc_id": section.doc_id, "node": section.node}
        events.append({
            "event_no": len(events) + 1,
            "channel": "PRESENT",
            "task": "legal-graph-presentation",
            "decision": "selected",
            "reason_code": "selected",
            "raw_coordinate": deepcopy(identity),
            "article_coordinate": deepcopy(identity),
            "source_coordinate": source,
            "trigger_type": "legal_graph_projection_ids",
            "trigger_value": list(provenance.get("projection_ids") or ()),
            "rank": rank,
            "score": None,
            "mandatory": True,
            "detail": {
                "origin": "legal-graph-v1",
                "generation_id": graph_meta.get("generation_id") or "",
            },
        })

    value = {
        key: deepcopy(item)
        for key, item in capture.items()
        if key not in {"capture_sha256", "stage_ledger", "events",
                       "event_reason_counts"}
    }
    value["stage_ledger"] = new_ledger
    value["events"] = events
    value["event_reason_counts"] = dict(sorted(Counter(
        row["reason_code"] for row in events
    ).items()))
    value["capture_sha256"] = stage_ledger.deterministic_sha256(value)
    article_reachability.validate_capture(value)
    expected = {
        canonicalize((section.doc_id, section.node)) for section in sections
    }
    actual = {
        (row["doc_id"], row["node"])
        for row in new_ledger["stages"][-1]["after"]
    }
    if actual != expected:
        raise ValueError("article reachability final set differs from sections")
    return value


def _replay_stage(
    recorder: stage_ledger.StageLedgerRecorder,
    row: Mapping[str, Any],
    *,
    stage_id: str | None = None,
) -> None:
    receipts = [
        (
            (
                receipt["identity"]["doc_id"],
                receipt["identity"]["node"],
            ),
            receipt["reason"],
        )
        for receipt in row.get("discard_receipts") or ()
    ]
    occurrences = row.get("occurrence_counts") or {}
    kwargs: dict[str, Any] = {
        "parent_stage_ids": tuple(row.get("parent_stage_ids") or ()),
        "executed": bool(row.get("executed")),
        "skip_reason": str(row.get("skip_reason") or ""),
        "discard_reasons": receipts,
        "before_occurrence_count": int(occurrences.get("before") or 0),
        "after_occurrence_count": int(occurrences.get("after") or 0),
    }
    if not kwargs["parent_stage_ids"]:
        kwargs["before_coordinates"] = list(row.get("before") or ())
    recorder.record_stage(
        stage_id or str(row["stage_id"]),
        str(row["kind"]),
        list(row.get("after") or ()),
        **kwargs,
    )
