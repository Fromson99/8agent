"""회수 좌표를 LLM이 둘러볼 계층형 탐색 범위로 바꾼다.

검색 채널이 내는 ``(doc_id, node)``는 정답이나 인용이 아니다. 이 모듈은 그
좌표들을 문서 트리에 다시 꽂는다. 항 좌표를 조로 합치지 않는다. 조·항은 각각
선택할 수 있고, 조를 고르면 그 아래 전체, 항을 고르면 그 항 아래 전체가 열린다.

    회수 좌표 여러 개
          ↓
    문서 → 조 → 항(각 회수 노드가 선택 단위)    # ExplorationMenu
          ↓ LLM은 R1, R2 같은 범위만 선택
    선택한 조의 Heading + 하위 계층 전체       # committed Section의 재료

검색기 점수는 이 단계의 계약이 아니다. 앞단이 후보 수를 제한할 때만 쓰고, 선택
메뉴에는 경로·원문 윤곽·실제 참조 관계만 보인다. 서로 다른 문서/조를 한 묶음처럼
보이게 하지 않으며, 둘 사이에 DB 간선이 있을 때만 ``E`` 간선으로 표시한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index


_ARTICLE_RE = re.compile(r"^제\s*\d+(?:-\d+)?조(?:의\s*\d+)?$")
_PARAGRAPH_RE = re.compile(r"^(?:제\s*\d+항|[①-⑳])$")
BODY_PREVIEW_CHARS_MAX = int(control_value("exploration.body_preview_chars_max"))
MATCH_CONTEXT_CHARS_MAX = int(control_value("exploration.match_context_chars_max"))
CONNECTED_RANGES_MAX = int(control_value("exploration.connected_ranges_max"))


def _label(node: dict) -> str:
    surface = str(node.get("surface") or "").strip()
    title = str(node.get("title") or "").strip()
    if surface and title and surface not in title:
        return f"{surface} {title}"
    return title or surface


def selection_root(view, node_id):
    """좌표를 선택 가능한 가장 가까운 조·항 단위로 맞춘다.

    조와 항은 **그 좌표 그대로** 유지한다. 호·목·본문처럼 더 작은 좌표만 가장
    가까운 항(없으면 조)으로 올린다. 따라서 제1항과 제2항이 회수되면 둘은 합쳐지지
    않고 제433조 아래의 별도 선택 가지가 된다. 조 체계가 아닌 보고서·서식의
    Heading은 원래 좌표를 유지한다. 문서명은 가상 루트라 선택 대상이 아니다.
    """
    original = node_id
    node = view.by_id.get(node_id)
    seen: set = set()
    while node is not None and node.get("id") not in seen:
        seen.add(node.get("id"))
        surface = str(node.get("surface") or "").strip()
        if (_ARTICLE_RE.fullmatch(surface)
                or _PARAGRAPH_RE.fullmatch(surface)):
            return node.get("id")
        node = view.by_id.get(node.get("parent"))
    return original


def subtree_text(view, node_id, *, cap: int | None) -> str:
    """조의 Heading을 첫 줄에 명시하고 그 아래 원문 계층 전체를 붙인다."""
    node = view.by_id.get(node_id)
    if node is None:
        return ""
    # 항만 선택해도 소속 조의 제목을 잃지 않도록 전체 구조 경로를 머리에 둔다.
    # 예: ``제433조 정관변경의 방법 ▸ ①``.
    heading = view.path(node_id) or _label(node)
    head = f"▸ {heading}" if heading else "▸ (제목 없음)"
    # 선택 뒤에는 cap=None을 쓴다. 회수 단계의 데이터 절단값 때문에 같은 조의
    # 뒷 항·호가 사라지면 "조를 선택하면 하위 전체"라는 계약이 거짓이 된다.
    # 선택 전 메뉴 미리보기만 명시적인 cap을 가진다.
    left = (10 ** 12 if cap is None else max(0, cap - len(head) - 1))
    body = view.section_outline(node, cap=left)
    return head + (("\n" + body) if body else "")


@dataclass
class ExplorationRange:
    id: str
    doc_id: str
    doc: str
    node: object
    path: str
    heading: str
    page: object = None
    channels: list[str] = field(default_factory=list)
    matched: list[dict] = field(default_factory=list)
    candidate_coordinates: list[dict] = field(default_factory=list)
    excerpt: str = ""
    signals: list[dict] = field(default_factory=list)

    def as_dict(self, *, include_outline: bool = True) -> dict:
        row = {
            "id": self.id, "doc_id": self.doc_id, "doc": self.doc,
            "node": self.node, "path": self.path, "heading": self.heading,
            "page": self.page, "channels": list(self.channels),
            "matched": list(self.matched),
            "signals": list(self.signals),
            "candidate_coordinates": list(self.candidate_coordinates),
            "selection_contract": "select-provision-includes-heading-and-entire-subtree",
        }
        return row


@dataclass
class ExplorationMenu:
    ranges: list[ExplorationRange]
    edges: list[dict]

    def as_dict(self, *, include_outline: bool = False) -> dict:
        documents: list[dict] = []
        by_doc: dict[str, dict] = {}
        for row in self.ranges:
            doc = by_doc.get(row.doc_id)
            if doc is None:
                doc = {"doc_id": row.doc_id, "doc": row.doc, "ranges": []}
                by_doc[row.doc_id] = doc
                documents.append(doc)
            doc["ranges"].append(row.as_dict(include_outline=include_outline))
        return {
            "contract": "retrieval-defines-exploration-range",
            "selection_unit": "article-or-paragraph; original-heading-for-non-law-docs",
            "selected_range_expands": "selected-provision-heading-and-entire-subtree",
            "selected_range_also_selects": "incident-edges",
            "documents": documents,
            "edges": list(self.edges),
        }


def _range_for_coordinate(index: Index, doc_id: str, node_id,
                          roots: dict[tuple[str, object], str]) -> str | None:
    view = index.docs.get(doc_id)
    if view is None or node_id not in view.by_id:
        return None
    # 간선이 항 아래 호에서 출발해도, 탐색 메뉴에 그 항(또는 조)이 있으면 가장
    # 가까운 선택 가능 조상으로 연결한다.
    current = node_id
    seen: set = set()
    while current is not None and current not in seen:
        seen.add(current)
        if (doc_id, current) in roots:
            return roots[(doc_id, current)]
        current = (view.by_id.get(current) or {}).get("parent")
    return None


def _own_excerpt(view, node_id, cap: int = BODY_PREVIEW_CHARS_MAX) -> str:
    """선택 노드가 직접 소유한 본문 첫머리. 자식 원문을 중복 출력하지 않는다."""
    node = view.by_id.get(node_id) or {}
    span = node.get("span") or [0, 0]
    parts: list[str] = []
    for block_id in range(span[0], max(span[1], span[0] + 1)):
        owner = view.owner(block_id)
        if owner is not None and owner.get("id") != node_id:
            continue
        text = str((view.block_by_idx.get(block_id) or {}).get("text") or "").strip()
        if text:
            parts.append(text)
        if sum(len(item) for item in parts) >= cap:
            break
    return " ".join(parts)[:cap]


def _packed_location(text: str, needle: str) -> tuple[int, int] | None:
    """공백 차이를 무시하고 needle의 원문 좌표를 되찾는다."""
    chars: list[str] = []
    positions: list[int] = []
    for pos, char in enumerate(text):
        if char.isspace():
            continue
        chars.append(char.casefold())
        positions.append(pos)
    wanted = "".join(char.casefold() for char in needle if not char.isspace())
    if not wanted:
        return None
    start = "".join(chars).find(wanted)
    if start < 0:
        return None
    end = start + len(wanted) - 1
    return positions[start], positions[end] + 1


def _context(text: str, start: int, end: int,
             cap: int = MATCH_CONTEXT_CHARS_MAX) -> str:
    room = max(0, cap - (end - start))
    left = min(start, room // 2)
    right = min(len(text) - end, room - left)
    value = text[start - left:end + right].replace("\n", " ").strip()
    return ("…" if start - left > 0 else "") + value + \
        ("…" if end + right < len(text) else "")


def _role(item: dict) -> str:
    label = str(item.get("label") or "")
    match = re.search(r"\[([A-Z_/]+)\]\s*$", label)
    if match:
        return match.group(1)
    kind = str(item.get("kind") or "")
    return {
        "general_keyword": "KEYWORD",
        "literal_fragment": "LITERAL",
        "section": "STRUCTURE",
        "document": "DOCUMENT",
    }.get(kind, kind.upper() or "MATCH")


def _signal_label(item: dict) -> str:
    return re.sub(r"\s*\[[A-Z_/]+\]\s*$", "",
                  str(item.get("label") or "")).strip()


def _signals(view, node_id, matched: list[dict]) -> list[dict]:
    """구조화 객체가 이 조·항의 어느 원문에 걸렸는지 짧게 표시한다."""
    node = view.by_id.get(node_id)
    text = view.section_text(node, cap=10 ** 12) if node is not None else ""
    out: list[dict] = []
    seen: set[tuple] = set()
    for item in matched:
        if item.get("kind") == "relation":
            continue
        label = _signal_label(item)
        surface = str(item.get("surface") or "").strip()
        needles = [label]
        if item.get("kind") == "general_keyword":
            needles = [part.strip() for part in surface.split("·") if part.strip()]
        elif surface and len(surface) <= 40:
            needles.append(surface)
        location = None
        needle_hit = ""
        for needle in sorted(set(needles), key=len, reverse=True):
            location = _packed_location(text, needle)
            if location:
                needle_hit = needle
                break
        role = _role(item)
        context = _context(text, *location) if location else ""
        key = (role, label or needle_hit, context)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "role": role, "label": label or needle_hit or surface,
            "query_surface": surface, "matched_text": needle_hit,
            "context": context, "via": str(item.get("via") or ""),
        })
    return out


def _edges(index: Index, ranges: list[ExplorationRange],
           origin_edges: list[dict]) -> list[dict]:
    roots = {(row.doc_id, row.node): row.id for row in ranges}
    out: list[dict] = []
    seen: set[tuple] = set()

    def endpoint(doc_id, node_id, range_id) -> str:
        if range_id:
            return range_id
        view = index.docs.get(doc_id)
        return f"{view.name} ▸ {view.path(node_id)}" if view else str(doc_id)

    def push(src_doc, src, dst_doc, dst, edge, *, dangling: bool = False) -> None:
        from_id = _range_for_coordinate(index, src_doc, src, roots)
        to_id = _range_for_coordinate(index, dst_doc, dst, roots)
        if (not from_id and not to_id) or (not dangling and (not from_id or not to_id)) \
                or (from_id and from_id == to_id):
            return
        rel = str(edge.get("rel") or "인용")
        surface = str(edge.get("surface") or "")
        key = (src_doc, src, dst_doc, dst, rel, surface)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "id": f"E{len(out) + 1}", "kind": "edge",
            "from": endpoint(src_doc, src, from_id),
            "to": endpoint(dst_doc, dst, to_id),
            "relation": rel, "surface": surface,
            "src_doc": src_doc, "src": src,
            "dst_doc": dst_doc, "dst": dst,
        })

    for doc_id, edges in index.ref_edges().items():
        for edge in edges or []:
            push(doc_id, edge.get("src"), doc_id, edge.get("dst"), edge)
    for edge in index.cross_ref_edges():
        push(edge.get("src_doc"), edge.get("src"),
             edge.get("dst_doc"), edge.get("dst"), edge)
    # 연결 보충으로 들어온 조·항은 상대편 R이 전체 메뉴 상한에서 잘려도, 자신을
    # 데려온 간선을 잃지 않는다. 한쪽 끝은 사람이 읽는 문서 경로로 표시한다.
    for edge in origin_edges:
        push(edge.get("src_doc"), edge.get("src"),
             edge.get("dst_doc"), edge.get("dst"), edge, dangling=True)
    return out


def build(index: Index, coordinate_options: Iterable[dict]) -> ExplorationMenu:
    """평면 좌표 옵션을 문서/조 계층으로 접는다.

    입력 순서는 앞단 회수기가 만든 제한된 탐색 순서를 보존한다. 여기서 새 점수를
    계산하거나 서로 다른 조의 집합을 Bundle로 만들지 않는다.
    """
    grouped: dict[tuple[str, object], dict] = {}
    order: list[tuple[str, object]] = []
    origin_edges: list[dict] = []
    for option in coordinate_options:
        doc_id, node_id = option.get("doc_id"), option.get("node")
        view = index.docs.get(doc_id)
        if view is None or node_id not in view.by_id:
            continue
        root = selection_root(view, node_id)
        root_node = view.by_id.get(root)
        if root_node is None:
            continue
        key = (doc_id, root)
        row = grouped.get(key)
        if row is None:
            row = {
                "doc_id": doc_id, "doc": view.name, "node": root,
                "path": view.path(root) or view.name,
                "heading": _label(root_node), "page": root_node.get("page"),
                "channels": [], "matched": [], "candidate_coordinates": [],
            }
            grouped[key] = row
            order.append(key)
        row["channels"] = list(dict.fromkeys(
            [*row["channels"], *(option.get("channels") or [])]))
        have = {str(item.get("object_id")) for item in row["matched"]}
        row["matched"].extend(
            item for item in option.get("matched") or []
            if str(item.get("object_id")) not in have)
        for edge in option.get("origin_edges") or []:
            if edge not in origin_edges:
                origin_edges.append(edge)
        coord = {"doc_id": doc_id, "node": node_id,
                 "path": option.get("path") or view.path(node_id),
                 "category": option.get("category") or ""}
        if coord not in row["candidate_coordinates"]:
            row["candidate_coordinates"].append(coord)

    ranges: list[ExplorationRange] = []
    for pos, key in enumerate(order, start=1):
        row = grouped[key]
        view = index.docs[row["doc_id"]]
        ranges.append(ExplorationRange(
            id=f"R{pos}", **row,
            excerpt=_own_excerpt(view, row["node"]),
            signals=_signals(view, row["node"], row["matched"]),
        ))
    return ExplorationMenu(ranges=ranges, edges=_edges(index, ranges, origin_edges))


def connected_options(index: Index, coordinate_options: Iterable[dict], *,
                      question: str = "", cap: int = CONNECTED_RANGES_MAX) -> list[dict]:
    """초기 회수 조·항과 실제로 이어진 1-hop 조·항을 선택 메뉴에 보충한다.

    방향을 둘 다 본다. ``제434조 → 제433조제1항``처럼 특별규정 쪽이 기본규정을
    가리키는 경우, 질문이 제433조제1항에 먼저 닿아도 역방향으로 제434조를 탐색할
    수 있어야 하기 때문이다. 연결 자체가 없는 유사 조문은 추가하지 않는다.
    """
    base = list(coordinate_options)
    units: list[tuple[str, object]] = []
    base_units: set[tuple[str, object]] = set()
    base_docs: set[str] = set()
    for option in base:
        doc_id, node_id = option.get("doc_id"), option.get("node")
        view = index.docs.get(doc_id)
        if view is None or node_id not in view.by_id:
            continue
        unit = (doc_id, selection_root(view, node_id))
        if unit not in base_units:
            units.append(unit)
            base_units.add(unit)
        base_docs.add(doc_id)

    incoming: dict[tuple[str, object], list[tuple]] = {}
    outgoing: dict[tuple[str, object], list[tuple]] = {}

    def index_edge(src_doc, src, dst_doc, dst, edge) -> None:
        src_view, dst_view = index.docs.get(src_doc), index.docs.get(dst_doc)
        if (src_view is None or dst_view is None or src not in src_view.by_id
                or dst not in dst_view.by_id):
            return
        src_unit = (src_doc, selection_root(src_view, src))
        dst_unit = (dst_doc, selection_root(dst_view, dst))
        if src_unit == dst_unit:
            return
        payload = (src_unit, dst_unit, edge)
        outgoing.setdefault(src_unit, []).append(payload)
        incoming.setdefault(dst_unit, []).append(payload)

    # 문서 내 간선은 초기 후보 문서만 색인하면 충분하다. 문서 간 간선은 한쪽이
    # 초기 후보 문서일 수 있으므로 전체 확정 간선에서 양 끝을 본다.
    for doc_id in base_docs:
        for edge in index.ref_edges().get(doc_id, ()):
            index_edge(doc_id, edge.get("src"), doc_id, edge.get("dst"), edge)
    for edge in index.cross_ref_edges():
        if edge.get("src_doc") not in base_docs and edge.get("dst_doc") not in base_docs:
            continue
        index_edge(edge.get("src_doc"), edge.get("src"),
                   edge.get("dst_doc"), edge.get("dst"), edge)

    out: list[dict] = []
    seen = set(base_units)

    def push(target: tuple[str, object], edge: dict, direction: str,
             peer: tuple[str, object]) -> None:
        if target in seen:
            return
        doc_id, node_id = target
        view = index.docs.get(doc_id)
        node = view.by_id.get(node_id) if view else None
        peer_view = index.docs.get(peer[0])
        if view is None or node is None or peer_view is None:
            return
        seen.add(target)
        rel = str(edge.get("rel") or "인용")
        surface = str(edge.get("surface") or "")
        arrow = (f"{view.name} {view.path(node_id)} --{rel}--> "
                 f"{peer_view.name} {peer_view.path(peer[1])}") \
            if direction == "incoming" else \
            (f"{peer_view.name} {peer_view.path(peer[1])} --{rel}--> "
             f"{view.name} {view.path(node_id)}")
        src_doc = target[0] if direction == "incoming" else peer[0]
        dst_doc = peer[0] if direction == "incoming" else target[0]
        origin_edge = {
            "src_doc": edge.get("src_doc") or src_doc,
            "src": edge.get("src"),
            "dst_doc": edge.get("dst_doc") or dst_doc,
            "dst": edge.get("dst"),
            "rel": rel, "surface": surface,
        }
        out.append({
            "id": f"EDGE{len(out) + 1}", "doc_id": doc_id, "node": node_id,
            "doc": view.name, "path": view.path(node_id) or view.name,
            "channels": ["relation"], "category": "relation",
            "intersection_count": 1,
            "origin_edges": [origin_edge],
            "matched": [{
                "surface": surface, "kind": "relation", "label": arrow,
                "via": f"document-edge:{direction}",
                "object_id": (f"edge:{peer[0]}:{peer[1]}:{doc_id}:{node_id}:"
                              f"{direction}"),
            }],
        })

    # 후보 순서를 보존하며 incoming(특별규정→기본규정)을 먼저 본다.
    for unit in units:
        for src_unit, _dst_unit, edge in incoming.get(unit, ()):
            push(src_unit, edge, "incoming", unit)
        for _src_unit, dst_unit, edge in outgoing.get(unit, ()):
            push(dst_unit, edge, "outgoing", unit)
    if len(out) <= cap:
        return out

    # 연결 후보가 상한을 넘으면 기존 좌표 규약과 같이 실제 연결 목적지 안에서만
    # Vector로 줄인다. 이 점수는 메뉴에 보이지 않고 탐색 범위 절단에만 쓰인다.
    from lawrag.core.rag import vector as vector_mod
    coords = {(row["doc_id"], row["node"]) for row in out}
    ranked = vector_mod.search(
        question, topk=cap, coordinates=coords, minimum=-1.0) if question else []
    order = {(doc_id, node): pos for pos, (doc_id, node, _score) in enumerate(ranked)}
    chosen = sorted(
        enumerate(out),
        key=lambda item: (order.get((item[1]["doc_id"], item[1]["node"]), cap + item[0]),
                          item[0]))[:cap]
    return [row for _pos, row in chosen]


def prompt_tree(menu: ExplorationMenu) -> str:
    """LLM 선택기에 줄 트리. 범위를 평면 카드로 되돌리지 않는다."""
    lines: list[str] = []
    by_doc: dict[str, list[ExplorationRange]] = {}
    for row in menu.ranges:
        by_doc.setdefault(row.doc_id, []).append(row)
    for doc_id, rows in by_doc.items():
        lines.append(f"문서 {doc_id} | {rows[0].doc}")
        # 회수된 조·항과 그 조상만으로 문서 트리를 복원한다. 조상은 경로 표시에만
        # 쓰고 R id가 있는 실제 회수 노드만 선택할 수 있다.
        nodes: dict[object, dict] = {}
        roots: list[object] = []
        # build 시의 node ids만 있어도 조상 체인은 menu 밖 Index 없이 복원할 수 없으므로
        # range에 path_parts를 중복 싣지 않는 대신 path 문자열을 안전한 표시 폴백으로 둔다.
        # 실제 트리 구조는 candidate path의 ' ▸ ' 단위로 세운다.
        for row in rows:
            parts = [part for part in row.path.split(" ▸ ") if part]
            parent_key = None
            for depth, part in enumerate(parts):
                key = (parent_key, part)
                if key not in nodes:
                    nodes[key] = {"label": part, "children": [], "row": None}
                    if parent_key is None:
                        roots.append(key)
                    else:
                        nodes[parent_key]["children"].append(key)
                parent_key = key
            if parent_key is not None:
                nodes[parent_key]["row"] = row

        def render(key, prefix: str, last: bool) -> None:
            node = nodes[key]
            row = node["row"]
            branch = "└─" if last else "├─"
            if row is None:
                lines.append(f"{prefix}{branch} {node['label']}")
            else:
                lines.append(
                    f"{prefix}{branch} {row.id} [선택 가능; 하위 전체 포함] {node['label']}")
                signal_prefix = prefix + ("   " if last else "│  ")
                if row.signals:
                    for signal in row.signals:
                        query = (f" ← 질문 '{signal['query_surface']}'"
                                 if signal.get("query_surface") else "")
                        lines.append(
                            f"{signal_prefix}   매칭: [{signal['role']}] "
                            f"{signal['label']}{query}")
                        if signal.get("context"):
                            lines.append(
                                f"{signal_prefix}     원문 구간: {signal['context']}")
                if row.excerpt and not any(signal.get("context") for signal in row.signals):
                    lines.append(f"{signal_prefix}   본문 첫머리: {row.excerpt}")
            children = node["children"]
            child_prefix = prefix + ("   " if last else "│  ")
            for pos, child in enumerate(children):
                render(child, child_prefix, pos == len(children) - 1)

        for pos, root in enumerate(roots):
            render(root, "", pos == len(roots) - 1)
    if menu.edges:
        lines.append("\n[간선 — R을 선택하면 그 R에 붙은 E도 함께 선택됨]")
        for edge in menu.edges:
            surface = f" '{edge['surface']}'" if edge.get("surface") else ""
            lines.append(
                f"{edge['id']}: {edge['from']} --{edge['relation']}{surface}--> "
                f"{edge['to']}")
    return "\n".join(lines)


def remove_descendant_picks(ranges: list[ExplorationRange], picks: list[str]) \
        -> tuple[list[str], list[str]]:
    """부모 조와 그 항을 함께 골랐으면 항 선택은 중복이므로 제거한다."""
    by_id = {row.id: row for row in ranges}
    selected = [by_id[pick] for pick in picks if pick in by_id]
    kept: list[str] = []
    removed: list[str] = []
    for row in selected:
        redundant = False
        for parent in selected:
            if parent.id == row.id or parent.doc_id != row.doc_id:
                continue
            prefix = parent.path + " ▸ "
            if row.path.startswith(prefix):
                redundant = True
                break
        (removed if redundant else kept).append(row.id)
    return kept, removed


def selected_edges(menu: ExplorationMenu, picks: list[str]) -> list[dict]:
    """선택된 조·항에 붙은 간선은 별도 LLM 선택 없이 함께 확정한다."""
    chosen = set(picks)
    return [edge for edge in menu.edges
            if edge.get("from") in chosen or edge.get("to") in chosen]
