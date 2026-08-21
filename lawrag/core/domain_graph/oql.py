"""1급 Concept Graph용 OQL(Ontology Query Language).

자연어 또는 LLM 출력은 SQL/Cypher가 되지 않는다. planner가 카탈로그의 pattern과
검증된 Concept ID 파라미터만 만들고, 실행기는 고정 handler의 prepared query만 쓴다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from .alignment import Alignment
from .store import GraphStore
from .tier1 import ASSERTION_ROLES, Tier1Registry


CATALOG = Path(__file__).with_name("oql_patterns.yaml")
LIMIT_CEILING = 50
PARAM_TYPES = frozenset({"concept_ids"})
HANDLERS = frozenset({
    "relation_between_concepts", "assertions_for_concept", "actor_obligations",
    "actions_on_object", "concept_definition",
})


def load(path: str | Path | None = None) -> list[dict]:
    blob = yaml.safe_load(Path(path or CATALOG).read_text(encoding="utf-8"))
    patterns = blob.get("patterns") or []
    seen = set()
    for pattern in patterns:
        validate_pattern(pattern)
        if pattern["id"] in seen:
            raise ValueError(f"OQL pattern id 중복: {pattern['id']}")
        seen.add(pattern["id"])
    return patterns


def validate_pattern(pattern: dict) -> None:
    pid = pattern.get("id")
    if not pid:
        raise ValueError("OQL pattern id 없음")
    if pattern.get("handler") not in HANDLERS:
        raise ValueError(f"{pid}: 허용되지 않은 handler")
    limit = pattern.get("limit")
    if not isinstance(limit, int) or not 1 <= limit <= LIMIT_CEILING:
        raise ValueError(f"{pid}: limit은 1..{LIMIT_CEILING}")
    names = set()
    for param in pattern.get("parameters") or []:
        name = param.get("name")
        if not name or name in names:
            raise ValueError(f"{pid}: parameter 이름 없음 또는 중복")
        names.add(name)
        if param.get("type") not in PARAM_TYPES:
            raise ValueError(f"{pid}: 허용되지 않은 parameter type")


def pattern_for_intent(intent: str, catalog: Optional[list[dict]] = None) -> dict | None:
    return next((p for p in (catalog or load()) if p.get("intent") == intent), None)


def plan(alignment: Alignment, catalog: Optional[list[dict]] = None) -> dict | None:
    """정렬 결과를 OQL로 만든다. 원 질문 문자열은 파라미터에 들어가지 않는다."""
    selected = alignment.selected
    if not selected:
        return None
    pattern = pattern_for_intent(alignment.intent, catalog)
    if pattern is None:
        return None
    ids = [c.concept_id for c in selected]
    if pattern["id"] == "relation_between_concepts":
        if len(ids) < 2:
            return None
        params = {"left_concept_ids": [ids[0]], "right_concept_ids": ids[1:]}
    elif pattern["id"] == "actor_obligations":
        actor = [c.concept_id for c in selected if c.role in ("actor", "unknown")]
        params = {"actor_concept_ids": actor or ids}
    elif pattern["id"] == "actions_on_object":
        objects = [c.concept_id for c in selected if c.role in ("object", "unknown")]
        params = {"object_concept_ids": objects or ids}
    else:
        params = {"concept_ids": ids}
    return {"pattern": pattern["id"], "params": params}


def validate_request(request: dict, pattern: dict, registry: Tier1Registry) -> dict:
    params = request.get("params") or {}
    declared = {p["name"]: p for p in pattern.get("parameters") or []}
    unknown = set(params) - set(declared)
    if unknown:
        raise ValueError(f"{pattern['id']}: 선언되지 않은 OQL parameter {sorted(unknown)}")
    active = registry.active_concepts
    clean = {}
    for name, spec in declared.items():
        value = params.get(name)
        if spec.get("required") and not value:
            raise ValueError(f"{pattern['id']}: 필수 parameter 누락 {name}")
        if spec["type"] == "concept_ids":
            if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
                raise ValueError(f"{pattern['id']}: {name}은 concept id 목록")
            ids = list(dict.fromkeys(value))[:12]
            if any(cid not in active for cid in ids):
                raise ValueError(f"{pattern['id']}: active가 아닌 concept id")
            clean[name] = ids
    return clean


def execute(store: GraphStore, registry: Tier1Registry, request: dict,
            catalog: Optional[list[dict]] = None) -> dict:
    patterns = catalog or load()
    pattern = next((p for p in patterns if p["id"] == request.get("pattern")), None)
    if pattern is None:
        raise ValueError(f"등록되지 않은 OQL pattern: {request.get('pattern')!r}")
    params = validate_request(request, pattern, registry)
    handler = pattern["handler"]
    if handler == "relation_between_concepts":
        aids = _intersect_assertions(store, params["left_concept_ids"],
                                     params["right_concept_ids"])
        rows = _assertion_rows(store, aids, pattern["limit"])
    elif handler == "assertions_for_concept":
        aids = _assertions_touching(store, params["concept_ids"])
        rows = _assertion_rows(store, aids, pattern["limit"])
    elif handler == "actor_obligations":
        aids = _assertions_by_role(store, "ACTOR", params["actor_concept_ids"])
        rows = _assertion_rows(store, aids, pattern["limit"])
    elif handler == "actions_on_object":
        aids = set()
        for role in ("OBJECT", "SUBJECT"):
            aids |= _assertions_by_role(store, role, params["object_concept_ids"])
        rows = _assertion_rows(store, aids, pattern["limit"])
    else:
        rows = [{"concept": registry.active_concepts[cid]} for cid in params["concept_ids"]]
    return {"pattern": pattern["id"], "params": params, "count": len(rows), "rows": rows}


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _active_assertion_ids(store: GraphStore) -> set[str]:
    return {r["id"] for r in store.conn.execute(
        "SELECT id FROM nodes WHERE kind='Assertion' "
        "AND json_extract(props,'$.knowledge_grade')=1 "
        "AND json_extract(props,'$.status')='active'")}


def _assertions_touching(store: GraphStore, ids: list[str]) -> set[str]:
    sql = ("SELECT DISTINCT src FROM edges WHERE kind IN (" +
           _placeholders(list(ASSERTION_ROLES)) + ") AND dst IN (" +
           _placeholders(ids) + ")")
    rows = store.conn.execute(sql, [*ASSERTION_ROLES, *ids])
    return {r["src"] for r in rows} & _active_assertion_ids(store)


def _assertions_by_role(store: GraphStore, role: str, ids: list[str]) -> set[str]:
    sql = f"SELECT DISTINCT src FROM edges WHERE kind=? AND dst IN ({_placeholders(ids)})"
    return {r["src"] for r in store.conn.execute(sql, [role, *ids])} \
        & _active_assertion_ids(store)


def _intersect_assertions(store: GraphStore, left: list[str], right: list[str]) -> set[str]:
    return _assertions_touching(store, left) & _assertions_touching(store, right)


def _assertion_rows(store: GraphStore, assertion_ids: set[str], limit: int) -> list[dict]:
    out = []
    for aid in sorted(assertion_ids)[:limit]:
        assertion = store.get_node(aid)
        if assertion is None:
            continue
        roles = {}
        for edge in store.neighbors(aid):
            if edge["kind"] in ASSERTION_ROLES:
                target = store.get_node(edge["dst"])
                if target:
                    roles.setdefault(edge["kind"], []).append({
                        "concept_id": target["id"], "label": target["label"],
                        "type": target["props"].get("concept_type", ""),
                    })
        sources = []
        for edge in store.neighbors(aid, kinds=("SUPPORTED_BY",)):
            section = store.get_node(edge["dst"])
            if section:
                doc_id = section["props"].get("doc_id", "")
                doc = store.get_node(f"document:{doc_id}")
                sources.append({"doc_id": doc_id, "doc": (doc or {}).get("label", doc_id),
                                "node": section["props"].get("id"),
                                "path": section["props"].get("path", section["label"]),
                                "page": section["props"].get("page")})
        out.append({"assertion_id": aid, "label": assertion["label"],
                    "confidence": assertion["props"].get("confidence", 0),
                    "roles": roles, "sources": sources})
    return out
