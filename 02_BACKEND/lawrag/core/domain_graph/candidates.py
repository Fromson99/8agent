"""로컬 그래프의 하위 등급 지식을 1급 승인 원장에 올린다."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from .store import GraphStore
from .tier1 import Tier1Registry, concept_id
from . import normative
from .uncertainty import claim_metadata


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


FRAME_ROLE_TYPES = {
    "HAS_ACTION": "action",
    "HAS_ACTOR": "domain_term",
    "HAS_OBJECT": "domain_term",
    "HAS_TARGET": "domain_term",
}
FRAME_ASSERTION_ROLES = {
    "HAS_ACTION": "PREDICATE",
    "HAS_ACTOR": "ACTOR",
    "HAS_OBJECT": "OBJECT",
    "HAS_TARGET": "TARGET",
}

REQUIREMENT_CONCEPT_TYPES = {
    "CONDITION": "condition",
    "EXCEPTION": "condition",
    "TIME": "temporal_constraint",
    "QUANTITY": "quantity",
    "METHOD": "method",
    "EFFECT": "legal_effect",
}


def _candidate_metadata(evidence_type: str, **extra) -> dict:
    return claim_metadata(
        evidence_type=evidence_type, claim_status="candidate",
        consumer_policy="candidate_only", confidence_status="unscored",
        **extra)


def _load_ledger(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "concepts": [], "relations": [], "assertions": []}


def _save_ledger(path: Path, blob: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")


def _candidate_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(x) for x in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def _clean_surface(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value.strip(" \t\r\n\"'“”‘’")


def _frame_slot_rows(store: GraphStore):
    """Frame의 원래 슬롯 문자열과 source 좌표를 한 행씩 낸다."""
    return store.conn.execute(
        "SELECT f.id AS frame_id,f.props AS frame_props,e.kind AS edge_kind,"
        "m.label AS surface FROM nodes f "
        "JOIN edges e ON e.src=f.id AND e.kind IN "
        "('HAS_ACTION','HAS_ACTOR','HAS_OBJECT','HAS_TARGET') "
        "JOIN nodes m ON m.id=e.dst WHERE f.kind='Frame' "
        "ORDER BY f.id,e.kind,e.id")


def stage_frame_concepts(graph_path: str | Path, candidate_path: str | Path,
                         canonical_path: str | Path, *, limit: int = 0) -> dict:
    """Frame 슬롯의 고유 표면형을 Concept 후보로 적재한다.

    여기서는 의미를 승인하거나 문구를 고치지 않는다. 같은 공백 정규형만 하나로
    접고, 원래 표면형·role·source 좌표를 candidate_basis에 보존한다. 이후 Haiku
    승인자가 재사용 가능한 개념인지 최종 판정한다.
    """
    graph_path, candidate_path, canonical_path = map(
        Path, (graph_path, candidate_path, canonical_path))
    ledger = _load_ledger(candidate_path)
    canonical = json.loads(canonical_path.read_text(encoding="utf-8")) \
        if canonical_path.is_file() else {"concepts": []}

    occupied: dict[str, list[dict]] = defaultdict(list)
    existing_ids = set()
    for row in [*(canonical.get("concepts") or []), *(ledger.get("concepts") or [])]:
        existing_ids.add(str(row.get("id") or "").removeprefix("concept:"))
        for surface in [row.get("label"), *(row.get("aliases") or [])]:
            if _norm(surface):
                occupied[_norm(surface)].append(row)

    grouped: dict[tuple[str, str], dict] = {}
    malformed = 0
    with GraphStore(graph_path, readonly=True) as store:
        for row in _frame_slot_rows(store):
            surface = _clean_surface(row["surface"])
            kind = str(row["edge_kind"])
            if len(_norm(surface)) < 2 or len(surface) > 240:
                malformed += 1
                continue
            props = json.loads(row["frame_props"] or "{}")
            key = (kind, _norm(surface))
            item = grouped.setdefault(key, {
                "surface": surface, "role": kind,
                "docs": set(), "evidence": [], "variants": set(),
            })
            item["variants"].add(surface)
            if props.get("doc_id"):
                item["docs"].add(str(props["doc_id"]))
            if len(item["evidence"]) < 12:
                item["evidence"].append({
                    "doc_id": props.get("doc_id"), "node": props.get("node"),
                    "frame_id": row["frame_id"],
                })

    staged, duplicates, type_conflicts = [], 0, 0
    # action을 먼저 적재한다. 동일 표면형이 다른 슬롯에도 있으면 predicate에 필요한
    # action 유형이 우선이며, 나머지 role은 Assertion에서 같은 Concept를 재사용한다.
    order = {"HAS_ACTION": 0, "HAS_ACTOR": 1, "HAS_OBJECT": 2, "HAS_TARGET": 3}
    for (_kind, _packed), item in sorted(
            grouped.items(), key=lambda kv: (order[kv[0][0]], kv[1]["surface"], kv[0][1])):
        kind, packed = item["role"], _norm(item["surface"])
        same = occupied.get(packed) or []
        wanted_type = FRAME_ROLE_TYPES[kind]
        if same:
            # 기존 action은 그대로 재사용한다. 같은 글자가 domain_term으로 먼저
            # 승인된 경우 action과 의미 유형이 충돌하므로 조용히 중복 승인하지 않고
            # 명시적으로 집계한다.
            if kind == "HAS_ACTION" and not any(
                    str(r.get("type") or "") == "action" for r in same):
                type_conflicts += 1
            else:
                duplicates += 1
            continue
        cid = _candidate_id("frame_concept", kind.lower(), packed)
        if cid in existing_ids:
            duplicates += 1
            continue
        staged.append({
            "id": cid, "label": item["surface"], "type": wanted_type,
            "aliases": sorted(item["variants"] - {item["surface"]}),
            "scope_docs": sorted(item["docs"]), "version": 1,
            "candidate_status": "pending",
            **_candidate_metadata("frame_slot_surface"),
            "candidate_basis": {
                "knowledge_grade": 2, "source": "frame_slots",
                "role": kind, "occurrences_sample": item["evidence"],
                "variants": sorted(item["variants"]),
            },
        })
        existing_ids.add(cid)
        occupied[packed].append(staged[-1])
        if limit and len(staged) >= limit:
            break

    ledger.setdefault("concepts", []).extend(staged)
    _save_ledger(candidate_path, ledger)
    return {
        "unique_frame_slots": len(grouped), "staged": len(staged),
        "duplicates": duplicates, "type_conflicts": type_conflicts,
        "malformed": malformed, "queue_concepts": len(ledger.get("concepts") or []),
        "candidate": str(candidate_path),
    }


def _surface_index(registry: Tier1Registry) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for cid, concept in registry.active_concepts.items():
        for surface in concept.surfaces:
            packed = _norm(surface)
            if packed and cid not in found[packed]:
                found[packed].append(cid)
    return found


def stage_frame_knowledge(graph_path: str | Path, candidate_path: str | Path,
                          canonical_path: str | Path, *, limit: int = 0) -> dict:
    """승인 Concept로 정확히 정규화되는 Frame과 taxonomy를 1급 후보로 조립한다.

    자연어를 쿼리나 ID로 만들지 않는다. Frame의 닫힌 role을 Assertion role로
    옮기고, 원 표면형이 유일하게 가리키는 active Concept ID만 바인딩한다.
    taxonomy의 IS_A도 양 끝이 유일하게 정규화되고 source 좌표가 있을 때만 올린다.
    """
    graph_path, candidate_path, canonical_path = map(
        Path, (graph_path, candidate_path, canonical_path))
    ledger = _load_ledger(candidate_path)
    registry = Tier1Registry.load(canonical_path)
    surfaces = _surface_index(registry)
    existing_relations = {str(r.get("id") or ""): r
                          for r in ledger.get("relations") or []}
    existing_assertions = {str(r.get("id") or ""): r
                           for r in ledger.get("assertions") or []}

    frames: dict[str, dict] = {}
    relations_by_pair: dict[tuple[str, str], dict] = {}
    ambiguous_slots = unmapped_slots = 0
    with GraphStore(graph_path, readonly=True) as store:
        for row in _frame_slot_rows(store):
            props = json.loads(row["frame_props"] or "{}")
            frame = frames.setdefault(row["frame_id"], {
                "props": props, "roles": defaultdict(list), "raw": {},
            })
            surface = _clean_surface(row["surface"])
            frame["raw"][row["edge_kind"]] = surface
            cids = surfaces.get(_norm(surface)) or []
            if row["edge_kind"] == "HAS_ACTION":
                cids = [cid for cid in cids
                        if registry.active_concepts[cid].type == "action"]
            if len(cids) == 1:
                role = FRAME_ASSERTION_ROLES[row["edge_kind"]]
                if cids[0] not in frame["roles"][role]:
                    frame["roles"][role].append(cids[0])
            elif len(cids) > 1:
                ambiguous_slots += 1
            else:
                unmapped_slots += 1

        tax_rows = store.conn.execute(
            "SELECT e.id,e.props,s.label AS src_label,d.label AS dst_label "
            "FROM edges e JOIN nodes s ON s.id=e.src JOIN nodes d ON d.id=e.dst "
            "WHERE e.kind='IS_A' ORDER BY e.id")
        for row in tax_rows:
            srcs, dsts = surfaces.get(_norm(row["src_label"])) or [], \
                surfaces.get(_norm(row["dst_label"])) or []
            if len(srcs) != 1 or len(dsts) != 1 or srcs[0] == dsts[0]:
                continue
            props = json.loads(row["props"] or "{}")
            if not props.get("doc_id") or props.get("node") is None:
                continue
            key = (srcs[0], dsts[0])
            item = relations_by_pair.setdefault(key, {"evidence": []})
            evidence = {"doc_id": str(props["doc_id"]), "node": props["node"]}
            if evidence not in item["evidence"] and len(item["evidence"]) < 24:
                item["evidence"].append(evidence)

    staged_assertions, skipped_predicate, skipped_thin = [], 0, 0
    for frame_id, frame in sorted(frames.items()):
        roles = {k: v for k, v in frame["roles"].items() if v}
        if not roles.get("PREDICATE"):
            skipped_predicate += 1
            continue
        if len(roles) < 2:
            skipped_thin += 1
            continue
        props, raw = frame["props"], frame["raw"]
        if not props.get("doc_id") or props.get("node") is None:
            continue
        for axis, role in normative.FACET_ROLE_BY_AXIS.items():
            cid = normative.concept_id_for(axis, props.get(axis))
            if cid and cid in registry.active_concepts:
                roles[role] = [cid]
        aid = _candidate_id("frame_assertion", frame_id)
        action_cue = raw.get("HAS_ACTION", "")
        safe_cues = [action_cue] if action_cue and len(action_cue) <= 120 else []
        if aid in existing_assertions:
            existing = existing_assertions[aid]
            # query cue는 명제를 여는 술어 표현만이다. OBJECT/TARGET을 cue로 넣으면
            # ``투자권유대행인`` 속 ``투자권유`` 하나로 무관한 적합성 Assertion이
            # 열렸다(전용 골든 unrelated-reporting).
            existing["query_cues"] = safe_cues
            existing["roles"] = roles
            basis = existing.setdefault("candidate_basis", {})
            basis["mode"] = props.get("mode", "")
            basis["function"] = props.get("function", "")
            basis["proviso"] = bool(props.get("proviso"))
            basis["role_labels"] = {
                role: [registry.active_concepts[cid].label for cid in cids]
                for role, cids in roles.items()
            }
            continue
        role_labels = {
            role: [registry.active_concepts[cid].label for cid in cids]
            for role, cids in roles.items()
        }
        staged_assertions.append({
            "id": aid, "roles": roles,
            "source": {"doc_id": str(props["doc_id"]), "node": props["node"],
                       "frame_id": frame_id},
            "confidence": 0.8, "query_cues": safe_cues,
            "note": " | ".join(f"{k.removeprefix('HAS_').lower()}={v}"
                               for k, v in raw.items() if v)[:1200],
            "version": 1, "candidate_status": "pending",
            **_candidate_metadata("llm_frame_slots_with_source_coordinate"),
            "candidate_basis": {
                "knowledge_grade": 2, "source": "llm_frame",
                "frame_id": frame_id, "raw_slots": raw,
                "role_labels": role_labels,
                "mode": props.get("mode", ""), "function": props.get("function", ""),
                "proviso": bool(props.get("proviso")),
            },
        })
        existing_assertions[aid] = staged_assertions[-1]
        if limit and len(staged_assertions) >= limit:
            break

    staged_relations = []
    for (src, dst), item in sorted(relations_by_pair.items()):
        rid = _candidate_id("taxonomy_relation", src, dst, "IS_A")
        if rid in existing_relations:
            existing = existing_relations[rid]
            existing["src_label"] = registry.active_concepts[src].label
            existing["dst_label"] = registry.active_concepts[dst].label
            continue
        staged_relations.append({
            "id": rid, "type": "IS_A", "src": src, "dst": dst,
            "src_label": registry.active_concepts[src].label,
            "dst_label": registry.active_concepts[dst].label,
            "evidence": item["evidence"], "confidence": 0.8,
            "candidate_status": "pending",
            **_candidate_metadata("taxonomy_candidate_with_source_coordinate"),
            "candidate_basis": {"knowledge_grade": 2, "source": "taxonomy_llm"},
        })
        existing_relations[rid] = staged_relations[-1]

    ledger.setdefault("relations", []).extend(staged_relations)
    ledger.setdefault("assertions", []).extend(staged_assertions)
    _save_ledger(candidate_path, ledger)
    return {
        "frames": len(frames), "staged_assertions": len(staged_assertions),
        "staged_relations": len(staged_relations),
        "skipped_no_predicate": skipped_predicate,
        "skipped_thin": skipped_thin,
        "unmapped_slots": unmapped_slots, "ambiguous_slots": ambiguous_slots,
        "queue_relations": len(ledger.get("relations") or []),
        "queue_assertions": len(ledger.get("assertions") or []),
        "candidate": str(candidate_path),
    }


def stage_normative_concepts(candidate_path: str | Path,
                            canonical_path: str | Path) -> dict:
    """닫힌 규범 양태·기능 Concept을 승인 대기열에 한 번만 적재한다."""
    candidate_path, canonical_path = map(Path, (candidate_path, canonical_path))
    ledger = _load_ledger(candidate_path)
    canonical = json.loads(canonical_path.read_text(encoding="utf-8")) \
        if canonical_path.is_file() else {"concepts": []}
    occupied = {
        concept_id(row.get("id"))
        for row in [*(canonical.get("concepts") or []),
                    *(ledger.get("concepts") or [])]
        if row.get("id")
    }
    staged = []
    for spec in normative.all_specs():
        cid = concept_id(spec["id"])
        if cid in occupied:
            continue
        staged.append({
            "id": cid.removeprefix("concept:"),
            "label": spec["label"], "type": spec["type"],
            "aliases": list(spec.get("aliases") or ()),
            "version": 1, "candidate_status": "pending",
            **_candidate_metadata("closed_normative_axis"),
            "candidate_basis": {
                "knowledge_grade": 1, "source": "normative_closed_axis",
            },
        })
        occupied.add(cid)
    ledger.setdefault("concepts", []).extend(staged)
    _save_ledger(candidate_path, ledger)
    return {"staged": len(staged), "queue_concepts": len(ledger.get("concepts") or []),
            "candidate": str(candidate_path)}


def stage_requirement_concepts(graph_path: str | Path, candidate_path: str | Path,
                               canonical_path: str | Path, *, limit: int = 0) -> dict:
    """Requirement span을 의미 확정 없이 typed Concept 후보로 적재한다.

    조건·예외는 trigger 하나(``경우``, ``다만``)가 재사용 가능한 개념이 아니므로
    근거 절 전체를 사용한다. 나머지는 정확 trigger를 label로 사용한다. 어느 쪽도
    active로 승격하지 않으며 원문 좌표와 가능한 오류를 함께 보존한다.
    """
    graph_path, candidate_path, canonical_path = map(
        Path, (graph_path, candidate_path, canonical_path))
    ledger = _load_ledger(candidate_path)
    canonical = _load_ledger(canonical_path)
    existing_ids = {
        str(row.get("id") or "").removeprefix("concept:")
        for row in [*(canonical.get("concepts") or []),
                    *(ledger.get("concepts") or [])]
    }
    occupied = {
        _norm(surface)
        for row in [*(canonical.get("concepts") or []),
                    *(ledger.get("concepts") or [])]
        for surface in [row.get("label"), *(row.get("aliases") or [])]
        if _norm(surface)
    }

    grouped: dict[tuple[str, str], dict] = {}
    malformed = 0
    with GraphStore(graph_path, readonly=True) as store:
        rows = store.conn.execute(
            "SELECT id,label,props FROM nodes WHERE kind='Requirement' ORDER BY id")
        for row in rows:
            props = json.loads(row["props"] or "{}")
            kind = str(props.get("kind") or "")
            ctype = REQUIREMENT_CONCEPT_TYPES.get(kind)
            label = _clean_surface(
                props.get("surface") if kind in ("CONDITION", "EXCEPTION")
                else props.get("trigger") or row["label"])
            if not ctype or len(_norm(label)) < 2 or len(label) > 240:
                malformed += 1
                continue
            key = (ctype, _norm(label))
            item = grouped.setdefault(key, {
                "label": label, "type": ctype, "kinds": set(),
                "docs": set(), "evidence": [],
            })
            item["kinds"].add(kind)
            if props.get("doc_id"):
                item["docs"].add(str(props["doc_id"]))
            evidence = {
                "doc_id": props.get("doc_id"), "node": props.get("node"),
                "block": props.get("block"), "start": props.get("start"),
                "end": props.get("end"), "requirement_id": row["id"],
            }
            if len(item["evidence"]) < 12 and evidence not in item["evidence"]:
                item["evidence"].append(evidence)

    staged, duplicates = [], 0
    for (ctype, packed), item in sorted(grouped.items(), key=lambda pair: pair[0]):
        if packed in occupied:
            duplicates += 1
            continue
        cid = _candidate_id("requirement_concept", ctype, packed)
        if cid in existing_ids:
            duplicates += 1
            continue
        staged.append({
            "id": cid, "label": item["label"], "type": ctype,
            "scope_docs": sorted(item["docs"]), "version": 1,
            "candidate_status": "pending",
            **_candidate_metadata(
                "rule_extracted_exact_source_span",
                possible_errors=[
                    "source_parser_error", "span_boundary_error",
                    "requirement_kind_misclassification",
                    "not_a_reusable_concept",
                ]),
            "candidate_basis": {
                "knowledge_grade": 3, "source": "requirement_span",
                "requirement_kinds": sorted(item["kinds"]),
                "occurrences_sample": item["evidence"],
            },
        })
        existing_ids.add(cid)
        occupied.add(packed)
        if limit and len(staged) >= limit:
            break

    ledger.setdefault("concepts", []).extend(staged)
    _save_ledger(candidate_path, ledger)
    return {
        "unique_requirement_surfaces": len(grouped), "staged": len(staged),
        "duplicates": duplicates, "malformed": malformed,
        "queue_concepts": len(ledger.get("concepts") or []),
        "candidate": str(candidate_path),
    }


def stage_grade2(graph_path: str | Path, candidate_path: str | Path,
                 canonical_path: str | Path, *, limit: int = 0) -> dict:
    """grade=2 Concept 전부를 candidates.json에 추가한다. 의미 판정은 하지 않는다."""
    graph_path, candidate_path, canonical_path = map(
        Path, (graph_path, candidate_path, canonical_path))
    ledger = json.loads(candidate_path.read_text(encoding="utf-8")) \
        if candidate_path.is_file() else {
            "schema_version": 1, "concepts": [], "relations": [], "assertions": []}
    canonical = json.loads(canonical_path.read_text(encoding="utf-8")) \
        if canonical_path.is_file() else {"concepts": []}
    existing_ids = {str(r.get("id") or "").removeprefix("concept:")
                    for r in ledger.get("concepts") or []}
    occupied = set()
    for row in [*(canonical.get("concepts") or []), *(ledger.get("concepts") or [])]:
        occupied.update(_norm(v) for v in
                        [row.get("label"), *(row.get("aliases") or [])] if _norm(v))

    staged, duplicate, malformed = [], 0, 0
    with GraphStore(graph_path, readonly=True) as store:
        rows = store.conn.execute(
            "SELECT id,label,props FROM nodes WHERE kind='Concept' "
            "AND json_extract(props,'$.knowledge_grade')=2 ORDER BY label,id")
        for row in rows:
            raw_id = str(row["id"]).removeprefix("concept:")
            label = str(row["label"] or "").strip()
            if not raw_id or not label:
                malformed += 1
                continue
            if raw_id in existing_ids or _norm(label) in occupied:
                duplicate += 1
                continue
            props = json.loads(row["props"] or "{}")
            staged.append({
                "id": raw_id, "label": label,
                "type": props.get("concept_type") or "domain_term",
                "scope_docs": list(props.get("scope_docs") or []),
                "version": 1, "candidate_status": "pending",
                **_candidate_metadata("derived_graph_concept"),
                "candidate_basis": {
                    "knowledge_grade": 2, "source": props.get("source", ""),
                    "prior_status": props.get("status", ""),
                    "prior_confidence": props.get("confidence", ""),
                    "note": str(props.get("note") or "")[:1200],
                    "graph_node": row["id"],
                },
            })
            existing_ids.add(raw_id)
            occupied.add(_norm(label))
            if limit and len(staged) >= limit:
                break
    ledger.setdefault("concepts", []).extend(staged)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return {"grade2": len(staged) + duplicate + malformed, "staged": len(staged),
            "duplicates": duplicate, "malformed": malformed,
            "queue_concepts": len(ledger.get("concepts") or []),
            "candidate": str(candidate_path)}
