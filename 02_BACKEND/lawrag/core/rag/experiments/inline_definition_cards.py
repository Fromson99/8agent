"""같은 문서·같은 적용 scope에서 조문 본문에 실제 등장하는 정의만 inline한다.

운영 배선이 아니라 ADR-0041 실험 부품이다. 정의조 전체를 독립 근거로 싣지 않고,
각 실체 조문 바로 아래에 그 조문이 사용한 저자 정의의 원문 좌표를 붙인다.
"""

from __future__ import annotations

import re

from lawrag.core.rag import definitions, legal_coordinates, taxonomy


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _ancestors(view, node_id) -> set:
    out, seen = set(), set()
    while node_id is not None and node_id not in seen:
        seen.add(node_id)
        out.add(node_id)
        node_id = (view.by_id.get(node_id) or {}).get("parent")
    return out


def _in_scope(view, definition: dict, node_id) -> bool:
    if definition.get("scope") == "doc":
        return True
    root = definition.get("scope_root")
    return root is not None and root in _ancestors(view, node_id)


def matching_definitions(index, doc_id: str, node_id) -> list[dict]:
    """선택 조문 본문에 실제 등장하고 그 조문에 적용되는 같은 문서 정의 전부."""
    view = index.docs[doc_id]
    node = view.by_id.get(node_id)
    if node is None or definitions.is_definition_node(view, node_id):
        return []
    provision = legal_coordinates.subtree_text(view, node_id, cap=None)
    packed = _pack(provision)
    if not packed:
        return []
    tx = taxonomy.current(index, None, {doc_id})
    rows = []
    for order, item in enumerate(definitions.defs(view)):
        # 이 실험의 계약은 "같은 문서의 정의조"다. 다른 실체 조문 안의
        # ``이하 X라 한다`` 같은 지역 별칭은 같은 문서라도 여기서 끌지 않는다.
        if not definitions.is_definition_node(view, item.get("node")):
            continue
        term = _pack(item.get("term"))
        position = packed.find(term) if term else -1
        if position < 0 or not _in_scope(view, item, node_id):
            continue
        source_node = item.get("node")
        definition_text = legal_coordinates.subtree_text(view, source_node, cap=None)
        if not definition_text:
            definition_text = str(item.get("source") or "").strip()
        parents = [row["term"] for row in tx.hypernyms(item["term"], grounded_only=False)
                   if row.get("doc_id") == doc_id and row.get("node") == source_node]
        children = [row["term"] for row in tx.hyponyms(item["term"], grounded_only=False)
                    if row.get("doc_id") == doc_id and row.get("node") == source_node]
        rows.append({
            "term": item["term"], "kind": item.get("kind"),
            "doc_id": doc_id, "doc": view.name, "node": source_node,
            "block": item.get("block"), "path": view.path(source_node),
            "scope": item.get("scope"), "scope_root": item.get("scope_root"),
            "definition": definition_text,
            "hypernyms": list(dict.fromkeys(parents)),
            "hyponyms": list(dict.fromkeys(children)),
            "matched_position": position, "_order": order,
        })
    rows.sort(key=lambda row: (row["matched_position"], -len(row["term"]), row["_order"]))
    out, seen = [], set()
    for row in rows:
        key = (row["term"], row["node"], row.get("block"))
        if key in seen:
            continue
        seen.add(key)
        row.pop("_order", None)
        out.append(row)
    return out


def render(rows: list[dict]) -> str:
    if not rows:
        return ""
    parts = [
        "\n\n[이 조문에서 실제 사용된 같은 문서의 정의]",
        "아래 항목은 이 조문 본문에 용어가 실제 등장하고 적용 scope가 맞는 저자 정의다. "
        "정의는 용어의 뜻을 해석하는 보조이고 독립적인 의무·예외 근거가 아니다.",
    ]
    for row in rows:
        parts.extend([
            f"\n- 용어: {row['term']}",
            f"  정의 위치: {row['path']}",
            f"  적용 범위: {row['scope']}",
        ])
        if row.get("hypernyms"):
            parts.append(f"  상위개념: {', '.join(row['hypernyms'])}")
        if row.get("hyponyms"):
            parts.append(f"  포함·하위개념: {', '.join(row['hyponyms'])}")
        parts.append("  정의 원문:\n" + "\n".join(
            "    " + line for line in str(row["definition"]).splitlines()))
    return "\n".join(parts)
