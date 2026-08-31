"""질문 문자열을 DB 검색 객체에 역으로 대조한 해석 후보표.

기존 Span 분해기는 질문만 보고 역할을 정한다. 이 모듈은 질문을 바꿔 쓰지 않고,
질문 안에 실제로 있는 문자열을 Document/Section/Concept/저자 정의/query_cue에
역조회한다. 같은 문자열의 여러 해석은 대안(OR)이고, 모델이 고른 서로 다른
문자열은 기존 Landing 좌표 교집합(AND)의 입력이 된다.

이 표는 정본이 아니다. ID는 한 질의 안에서만 유효한 닫힌 메뉴이고, 모델이 고른
ID도 새 동의어나 Concept를 자동 발행하지 않는다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace

from lawrag.core.domain_graph import spanparts
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag import definitions, switches
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index


MENTIONS_MAX = int(control_value("query_guide.mentions_max"))
READINGS_MAX = int(control_value("query_guide.readings_per_mention_max"))
PROMPT_CHARS_MAX = int(control_value("query_guide.prompt_chars_max"))
_DOC_TOKEN = re.compile(
    r"[가-힣A-Za-z0-9·]{2,30}?(?:시행세칙|시행규칙|시행령|법률|규정|규칙|세칙|"
    r"약관|조례|정관|지침|고시|법)"
)


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def enabled() -> bool:
    """평가 실행은 env 한 변수로 A/B하고, 평상시는 사용자 엔진 스위치를 따른다."""
    raw = os.environ.get("RAG_QUERY_GUIDE")
    if raw is None or raw == "":
        return switches.is_on("query_guide")
    return raw.strip().casefold() not in {"0", "false", "off", "no"}


@dataclass(frozen=True)
class Reading:
    id: str
    surface: str
    start: int
    end: int
    object_kind: str
    object_id: str
    label: str
    roles: tuple[str, ...]
    via: str
    context: str = ""
    global_count: int = 0
    scoped_count: int = 0

    def as_dict(self) -> dict:
        return {
            "id": self.id, "surface": self.surface,
            "start": self.start, "end": self.end,
            "object_kind": self.object_kind, "object_id": self.object_id,
            "label": self.label, "roles": list(self.roles), "via": self.via,
            "context": self.context, "global_count": self.global_count,
            "scoped_count": self.scoped_count,
        }


@dataclass(frozen=True)
class Guide:
    question: str
    readings: tuple[Reading, ...] = ()
    raw_reading_count: int = 0
    collapsed_reading_count: int = 0
    truncated: bool = False

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(row.id for row in self.readings)

    @property
    def by_id(self) -> dict[str, Reading]:
        return {row.id: row for row in self.readings}

    def selected(self, reading_ids) -> list[Reading]:
        table = self.by_id
        return [table[rid] for rid in reading_ids if rid in table]

    def as_prompt(self) -> str:
        if not self.readings:
            return ""
        grouped: dict[tuple[int, int, str], list[Reading]] = {}
        for row in self.readings:
            grouped.setdefault((row.start, row.end, row.surface), []).append(row)
        lines = [
            "[DB 역매칭 해석 후보]",
            "같은 M 안의 G들은 서로 다른 해석(OR)이다. 질문에 맞는 G만 고른다.",
            "후보가 없어도 질문의 다른 실제 Span은 기존 방식대로 추가할 수 있다.",
        ]
        for pos, ((start, end, surface), rows) in enumerate(grouped.items(), 1):
            lines.append(f'M{pos} | {surface!r} [{start}:{end}]')
            for row in rows:
                roles = "/".join(row.roles) or "unknown"
                counts = f"전역={row.global_count},현재범위={row.scoped_count}"
                detail = f" | {row.context}" if row.context else ""
                lines.append(
                    f"- {row.id} | {row.object_kind} | {row.label} | 역할={roles} | "
                    f"근거={row.via} | {counts}{detail}"
                )
        return "\n".join(lines)[:PROMPT_CHARS_MAX]

    def as_dict(self) -> dict:
        mentions = len({(r.start, r.end) for r in self.readings})
        return {
            "enabled": True, "mention_count": mentions,
            "reading_count": len(self.readings),
            "raw_reading_count": self.raw_reading_count,
            "collapsed_reading_count": self.collapsed_reading_count,
            "truncated": self.truncated,
            "readings": [row.as_dict() for row in self.readings],
        }


def _packed_question(question: str) -> tuple[str, list[int]]:
    chars, offsets = [], []
    for pos, char in enumerate(question):
        if char.isspace():
            continue
        chars.append(char.casefold())
        offsets.append(pos)
    return "".join(chars), offsets


def _original_range(offsets: list[int], start: int, end: int) -> tuple[int, int] | None:
    if not offsets or start < 0 or end <= start or end > len(offsets):
        return None
    return offsets[start], offsets[end - 1] + 1


def _ranges_for_keys(question: str, keys: set[str], max_len: int) \
        -> list[tuple[int, int, str]]:
    """4만 표면을 순회하지 않고 짧은 질문의 부분문자열만 사전에 조회한다."""
    packed, offsets = _packed_question(question)
    out = []
    for start in range(len(packed)):
        stop = min(len(packed), start + max_len)
        for end in range(start + 2, stop + 1):
            key = packed[start:end]
            if key not in keys:
                continue
            original = _original_range(offsets, start, end)
            if original is not None:
                out.append((*original, key))
    return out


def _concept_catalog(registry: Tier1Registry):
    cached = getattr(registry, "_query_guide_concepts", None)
    if cached is not None:
        return cached
    by_surface: dict[str, list[tuple[str, str]]] = {}
    roles: dict[str, set[str]] = {}
    coords: dict[str, set[tuple[str, object]]] = {}
    assertions: dict[str, set[str]] = {}
    for assertion in registry.active_assertions:
        pair = (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node"))
        for role, ids in assertion.roles.items():
            for cid in ids:
                roles.setdefault(cid, set()).add(role.lower())
                assertions.setdefault(cid, set()).add(assertion.id)
                if pair[0] and pair[1] is not None:
                    coords.setdefault(cid, set()).add(pair)
    max_len = 0
    for cid, concept in registry.active_concepts.items():
        for surface in concept.surfaces:
            key = _pack(surface)
            if len(key) < 2:
                continue
            by_surface.setdefault(key, []).append((cid, surface))
            max_len = max(max_len, len(key))
    cached = (by_surface, roles, coords, assertions, max_len)
    registry._query_guide_concepts = cached
    return cached


def _fragment_catalog(registry: Tier1Registry):
    cached = getattr(registry, "_query_guide_fragments", None)
    if cached is not None:
        return cached
    by_surface: dict[str, dict] = {}
    max_len = 0
    for assertion in registry.active_assertions:
        pair = (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node"))
        for cue in assertion.query_cues:
            key = _pack(cue)
            if len(key) < 2:
                continue
            row = by_surface.setdefault(key, {
                "surface": cue, "coordinates": set(), "assertions": set(),
            })
            if pair[0] and pair[1] is not None:
                row["coordinates"].add(pair)
            row["assertions"].add(assertion.id)
            max_len = max(max_len, len(key))
    cached = (by_surface, max_len)
    registry._query_guide_fragments = cached
    return cached


def _structure_catalog(index: Index):
    cached = getattr(index, "_query_guide_structure", None)
    if cached is not None:
        return cached
    by_surface: dict[str, list] = {}
    max_len = 0
    for entry in index.entries:
        if entry.kind != "제목" or len(entry.key) < 2:
            continue
        by_surface.setdefault(entry.key, []).append(entry)
        max_len = max(max_len, len(entry.key))
    cached = (by_surface, max_len)
    index._query_guide_structure = cached
    return cached


def _subsequence_score(needle: str, haystack: str) -> float:
    n, h = _pack(needle), _pack(haystack)
    if not n or not h:
        return 0.0
    positions, cursor = [], 0
    for char in n:
        found = h.find(char, cursor)
        if found < 0:
            return 0.0
        positions.append(found)
        cursor = found + 1
    span = positions[-1] - positions[0] + 1
    return 0.45 + 0.4 * len(n) / max(span, len(n))


def _scope_coordinates(anchors) -> set[tuple[str, object]]:
    return set(anchors.source_coordinates)


def build(index: Index, question: str, registry: Tier1Registry, anchors) -> Guide:
    """질문에 실제로 걸린 DB 객체만 모아 질의 한정 닫힌 해석 메뉴를 만든다."""
    pending: list[Reading] = []
    seen: set[tuple] = set()
    scoped_coords = _scope_coordinates(anchors)
    scoped_docs = set(anchors.doc_ids)

    def push(*, surface: str, start: int, end: int, object_kind: str,
             object_id: str, label: str, roles: tuple[str, ...], via: str,
             context: str = "", global_count: int = 0, scoped_count: int = 0):
        key = (start, end, object_kind, object_id, roles)
        if start < 0 or end <= start or end > len(question) or key in seen:
            return
        seen.add(key)
        pending.append(Reading(
            "", question[start:end], start, end, object_kind, object_id, label,
            roles, via, context, global_count, scoped_count,
        ))

    # Document: 정식 제목/승인 약칭은 결정론. DB에 없는 축약형은 기존 문서 메뉴와
    # 같은 닫힌 후보를 미리 보여 주되, approximate라고 명시한다.
    _packed_text, offsets = _packed_question(question)
    exact_doc_ranges = set()
    for start, end, doc_id, name in spanparts._document_mentions(index, question):
        original = _original_range(offsets, start, end)
        if original is None:
            continue
        os_, oe = original
        exact_doc_ranges.add((os_, oe))
        surface = question[os_:oe]
        via = "document-title" if _pack(surface) == spanparts._doc_fold(name) \
            else "approved-document-alias"
        push(surface=surface, start=os_, end=oe, object_kind="document",
             object_id=f"document:{doc_id}", label=name, roles=("document",),
             via=via, context=f"문서={name}", global_count=1,
             scoped_count=1 if not scoped_docs or doc_id in scoped_docs else 0)
    for match in _DOC_TOKEN.finditer(question):
        if (match.start(), match.end()) in exact_doc_ranges:
            continue
        ranked = sorted((
            (_subsequence_score(match.group(), view.name), doc_id, view.name)
            for doc_id, view in index.entry_docs.items()
        ), key=lambda row: (-row[0], len(_pack(row[2])), row[1]))
        for score, doc_id, name in [row for row in ranked if row[0] >= .50][:3]:
            push(surface=match.group(), start=match.start(), end=match.end(),
                 object_kind="document", object_id=f"document:{doc_id}",
                 label=name, roles=("document",), via="document-closed-candidate",
                 context=f"축약 표면점수={score:.3f}", global_count=1,
                 scoped_count=1 if not scoped_docs or doc_id in scoped_docs else 0)

    # Section 제목/TOC: 색인의 제목 표면을 그대로 역조회한다.
    structure, structure_max = _structure_catalog(index)
    for start, end, key in _ranges_for_keys(question, set(structure), structure_max):
        for entry in structure[key]:
            if not index.in_scope(entry.doc_id):
                continue
            if scoped_docs and entry.doc_id not in scoped_docs:
                continue
            if scoped_coords and (entry.doc_id, entry.node) not in scoped_coords:
                continue
            view = index.docs.get(entry.doc_id)
            path = view.path(entry.node) if view is not None else entry.value
            push(surface=question[start:end], start=start, end=end,
                 object_kind="section", object_id=f"section:{entry.doc_id}:{entry.node}",
                 label=entry.value, roles=("heading", "toc"), via="structure-title",
                 context=f"{entry.doc} | {path}", global_count=1,
                 scoped_count=1 if (not scoped_docs or entry.doc_id in scoped_docs) else 0)

    # 제N조제M항 등의 구조 좌표는 resolver가 이미 검증한 좌표/경로를 카드화한다.
    for locator in anchors.locators:
        cursor = 0
        while True:
            start = question.find(locator, cursor)
            if start < 0:
                break
            end = start + len(locator)
            for doc_id, node in anchors.source_coordinates:
                view = index.docs.get(doc_id)
                if view is None:
                    continue
                push(surface=locator, start=start, end=end, object_kind="section",
                     object_id=f"section:{doc_id}:{node}", label=view.path(node) or locator,
                     roles=("locator",), via="resolved-locator",
                     context=f"{view.name} | {view.path(node)}", global_count=1,
                     scoped_count=1)
            cursor = end

    # 1급 의미 객체: 같은 표면이 여러 Concept/역할이면 전부 같은 M의 OR 해석이다.
    concepts, roles, coordinates, assertion_ids, concept_max = _concept_catalog(registry)
    document_ranges = {(row.start, row.end) for row in pending
                       if row.object_kind == "document"}
    for start, end, key in _ranges_for_keys(question, set(concepts), concept_max):
        for cid, matched in concepts[key]:
            concept = registry.active_concepts[cid]
            coords = coordinates.get(cid, set())
            # 검색 좌표/역할이 없는 고아 Concept는 설명용 정본일 수는 있어도 이
            # 회수기에서 착지할 수 없다. 후보표에 넣으면 선택 뒤 빈손만 만든다.
            if not coords or not roles.get(cid):
                continue
            scoped = coords & scoped_coords if scoped_coords else (
                {pair for pair in coords if pair[0] in scoped_docs} if scoped_docs else coords)
            # 독립 의미 Span은 먼저 잡힌 문서/조문 범위 안의 값만 제시한다.
            # 단, 같은 질문 문자열 자체가 Document이기도 하면 문서냐 Concept냐를
            # 고르는 OR 후보이므로 전역 Concept 해석을 보존한다.
            if anchors.explicit and not scoped and (start, end) not in document_ranges:
                continue
            role_values = tuple(sorted(roles.get(cid) or {"unknown"}))
            push(surface=question[start:end], start=start, end=end,
                 object_kind="concept", object_id=cid, label=concept.label,
                 roles=role_values, via="concept-surface",
                 context=f"type={concept.type}; matched={matched}",
                 global_count=len(coords) or len(assertion_ids.get(cid, set())),
                 scoped_count=len(scoped))

    # 저자 정의는 의미 교집합 요소가 아니라 정의 좌표/지역 별칭 확장 장치다.
    for hit in definitions.query_hits(
            index, question, doc_ids=scoped_docs or None):
        surface_key = _pack(hit["term"])
        for start, end, key in _ranges_for_keys(question, {surface_key}, len(surface_key)):
            if key != surface_key:
                continue
            view = index.docs.get(hit["doc_id"])
            path = view.path(hit["node"]) if view is not None else str(hit["node"])
            push(surface=question[start:end], start=start, end=end,
                 object_kind="definition", object_id=f"definition:{hit['doc_id']}:{hit['node']}",
                 label=hit["term"], roles=("subject", "unknown"),
                 via="author-definition", context=f"{hit['doc']} | {path}",
                 global_count=1, scoped_count=1 if (
                     not scoped_docs or hit["doc_id"] in scoped_docs) else 0)

    # 승격하지 않은 본문 조각(query_cue): 연결된 본문 좌표 수를 보여 줄 뿐,
    # Concept처럼 가장하거나 새 역할을 확정하지 않는다.
    fragments, fragment_max = _fragment_catalog(registry)
    for start, end, key in _ranges_for_keys(question, set(fragments), fragment_max):
        row = fragments[key]
        coords = row["coordinates"]
        scoped = coords & scoped_coords if scoped_coords else (
            {pair for pair in coords if pair[0] in scoped_docs} if scoped_docs else coords)
        if anchors.explicit and not scoped and (start, end) not in document_ranges:
            continue
        push(surface=question[start:end], start=start, end=end,
             object_kind="literal_fragment", object_id=f"fragment:{key}",
             label=row["surface"],
             roles=("predicate", "condition", "effect", "unknown"),
             via="assertion-query-cue", global_count=len(coords),
             scoped_count=len(scoped))

    # 한 문자열 안에서는 현재 구조 범위에 실제 출현한 해석, 정본 exact 해석,
    # 그 다음 전역 출현 순으로만 자른다. 자름 값은 controls에 기록된다.
    groups: dict[tuple[int, int], list[Reading]] = {}
    for row in pending:
        groups.setdefault((row.start, row.end), []).append(row)
    # 긴 DB 표면 안의 짧은 DB 표면을 별도 AND 단서처럼 보이면 오염되기 쉽다.
    # 긴 표면 하나가 먼저 그 뜻을 대표하고, LLM은 필요하면 후보표 밖의 실제
    # 짧은 Span을 기존 자유 분해로 다시 추가할 수 있다.
    def mention_score(key):
        rows = groups[key]
        return (
            int(any(row.scoped_count > 0 for row in rows)),
            key[1] - key[0],
            max((row.scoped_count for row in rows), default=0),
            max((row.global_count for row in rows), default=0),
        )

    eligible_mentions = []
    for key in groups:
        nested = [other for other in groups if key != other and (
            (key[0] >= other[0] and key[1] <= other[1])
            or (other[0] >= key[0] and other[1] <= key[1])
        )]
        # 같은 포함 묶음에서 현재 구조 범위 출현 여부가 먼저 이기고, 같으면
        # 구체적인 긴 표면이 이긴다. 동점이면 안정적인 좌표 순서로 하나만 남긴다.
        rivals = [other for other in nested if mention_score(other) > mention_score(key)]
        tied_before = [other for other in nested
                       if mention_score(other) == mention_score(key) and other < key]
        if not rivals and not tied_before:
            eligible_mentions.append(key)
    ordered_mentions = sorted(
        eligible_mentions,
        key=lambda key: (key[0], -(key[1] - key[0]), key[1]),
    )[:MENTIONS_MAX]
    collapsed_count = sum(len(groups[mention]) for mention in eligible_mentions)
    final: list[Reading] = []
    for mention in ordered_mentions:
        rows = sorted(groups[mention], key=lambda row: (
            -int(row.scoped_count > 0),
            {"document": 0, "section": 1, "concept": 2,
             "definition": 3, "literal_fragment": 4}.get(row.object_kind, 9),
            -row.global_count,
            len(_pack(row.label)) if row.object_kind == "document" else 0,
            row.object_id,
        ))[:READINGS_MAX]
        final.extend(rows)
    final = [replace(row, id=f"QG{pos}") for pos, row in enumerate(final, 1)]
    return Guide(question, tuple(final), raw_reading_count=len(pending),
                 collapsed_reading_count=collapsed_count,
                 truncated=len(final) < collapsed_count)


def selected_document_ids(guide: Guide, spans, preliminary_doc_ids) -> set[str]:
    """같은 표면이 문서/Concept 중의적일 때 모델 선택으로 문서 스코프를 가른다."""
    docs = set(preliminary_doc_ids)
    table = guide.by_id
    selected = {rid for span in spans for rid in span.reading_ids if rid in table}
    by_range: dict[tuple[int, int], list[Reading]] = {}
    for row in guide.readings:
        by_range.setdefault((row.start, row.end), []).append(row)
    for rows in by_range.values():
        doc_rows = [row for row in rows if row.object_kind == "document"]
        if not doc_rows:
            continue
        chosen = [row for row in rows if row.id in selected]
        chosen_docs = [row for row in chosen if row.object_kind == "document"]
        chosen_non_docs = [row for row in chosen if row.object_kind != "document"]
        if chosen_non_docs and not chosen_docs:
            docs.difference_update(
                row.object_id.removeprefix("document:") for row in doc_rows)
        docs.update(row.object_id.removeprefix("document:") for row in chosen_docs)
    return docs
