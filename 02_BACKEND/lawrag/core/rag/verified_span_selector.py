"""Select only server-verified source spans from registry candidates.

This experiment-only component removes free-form citation generation from the
claim relevance selector.  The server creates exact source spans and gives the
model authority only to return IDs from a dynamic JSON-schema enum.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
PRESENTED_MAX = 20
POOL_MAX = 48
REGISTRY_MAX = 3
SELECTION_MAX = 3
INCUMBENT_CARDS_MAX = 12
SOURCE_WINDOW_CHARS = 2_400
SPAN_CHARS = 520
SPANS_PER_SOURCE_MAX = 6
INCUMBENT_CHARS = 700
OUTPUT_TOKENS_MAX = 900

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")

_SYSTEM = """너는 source registry와 최종 presentation 사이의 claim-citation 관련성 검사자다.

서버가 원문에서 잘라 hash와 offset을 검증한 [선택 가능한 verified span]만 판단한다. 원질문의
구체 claim을 직접 뒷받침하거나, 적용에 반드시 필요한 위임·예외·정의·companion span만 고른다.

다음은 고르지 않는다.
- 같은 단어만 포함한 다른 제도·다른 주체·다른 법률의 span
- 신청서·보고서 서식, 부칙, 일반 절차처럼 target claim을 닫지 않는 span
- [비선택 incumbent 참고 근거]가 이미 제공하는 근거를 단순 반복하는 span
- 최종 결론과 연결 경로를 설명할 수 없는 넓은 관련 규정

출력 권한은 selected_span_ids뿐이다. 반드시 schema enum에 있는 S로 시작하는 span_id만 그대로
복사한다. incumbent 참고 근거는 선택 대상이 아니며 ID도 없다. 인용문·조문 좌표·새 ID를 쓰지
않는다. 관련 span이 없으면 selected_span_ids를 빈 배열로 둔다."""


def _schema(span_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "selected_span_ids": {
                "type": "array",
                "items": {"type": "string", "enum": list(span_ids)},
                "maxItems": SELECTION_MAX,
                "uniqueItems": True,
            },
            "remaining_gap": {"type": "string"},
        },
        "required": ["selected_span_ids", "remaining_gap"],
        "additionalProperties": False,
    }


def _dedupe(rows: Iterable[termexplore.TermBranch], *, cap: int) \
        -> list[termexplore.TermBranch]:
    out: list[termexplore.TermBranch] = []
    seen: set[tuple] = set()
    for row in rows:
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
        if len(out) >= max(0, int(cap)):
            break
    return out


def _source(index: Index, row: termexplore.TermBranch) -> str:
    view = index.docs.get(row.doc_id)
    if view is None or row.node not in view.by_id:
        return str(row.body or "")
    return coordinates.subtree_text(view, row.node, cap=None)


def _window(text: str, question: str, *, cap: int) -> tuple[int, int]:
    if len(text) <= cap:
        return 0, len(text)
    for token in _TOKEN.findall(question):
        match = re.search(re.escape(token), text, flags=re.IGNORECASE)
        if match:
            start = max(0, match.start() - cap // 3)
            return start, min(len(text), start + cap)
    return 0, min(len(text), cap)


def _chunk_ranges(text: str, start: int, end: int, *, cap: int) \
        -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        stop = min(end, cursor + cap)
        if stop < end:
            fragment = text[cursor:stop]
            breaks = [fragment.rfind(mark) for mark in ("\n", "다. ", ". ")]
            boundary = max(breaks)
            if boundary >= cap // 2:
                stop = cursor + boundary + 1
        if stop <= cursor:
            stop = min(end, cursor + cap)
        ranges.append((cursor, stop))
        cursor = stop
        while cursor < end and text[cursor].isspace():
            cursor += 1
    return ranges


def _verified_spans(index: Index, rows: list[termexplore.TermBranch],
                    question: str) -> tuple[list[dict], dict[str, dict]]:
    public: list[dict] = []
    by_id: dict[str, dict] = {}
    serial = 1
    for row in rows[:REGISTRY_MAX]:
        source = _source(index, row)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        start, end = _window(source, question, cap=SOURCE_WINDOW_CHARS)
        ranges = _chunk_ranges(source, start, end, cap=SPAN_CHARS)
        for span_start, span_end in ranges[:SPANS_PER_SOURCE_MAX]:
            span_id = f"S{serial:02d}"
            serial += 1
            text = source[span_start:span_end]
            record = {
                "span_id": span_id,
                "coordinate": [row.doc_id, row.node],
                "document": row.doc,
                "path": row.path,
                "origin": row.origin,
                "source_sha256": source_hash,
                "start": span_start,
                "end": span_end,
                "text": text,
                "row": row,
            }
            by_id[span_id] = record
            public.append({key: value for key, value in record.items()
                           if key not in {"row", "coordinate"}})
    return public, by_id


def _reference_cards(index: Index, rows: list[termexplore.TermBranch],
                     question: str) -> list[dict]:
    cards = []
    for row in rows[:INCUMBENT_CARDS_MAX]:
        source = _source(index, row)
        start, end = _window(source, question, cap=INCUMBENT_CHARS)
        cards.append({
            "namespace": "reference_only_not_selectable",
            "document": row.doc,
            "path": row.path,
            "text": source[start:end],
        })
    return cards


def _validate(raw: object, by_id: dict[str, dict]) \
        -> tuple[list[dict], list[str]]:
    accepted: list[dict] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_coordinates: set[tuple] = set()
    for pos, value in enumerate(raw if isinstance(raw, list) else (), 1):
        if not isinstance(value, str):
            errors.append(f"span_id_not_string:{pos}")
            continue
        record = by_id.get(value)
        if record is None:
            errors.append(f"span_outside_menu:{value or pos}")
            continue
        if value in seen_ids:
            continue
        seen_ids.add(value)
        coordinate = tuple(record["coordinate"])
        if coordinate in seen_coordinates:
            continue
        seen_coordinates.add(coordinate)
        accepted.append({key: item for key, item in record.items()
                         if key != "row"})
        if len(accepted) >= SELECTION_MAX:
            break
    return accepted, errors


def _pool_rows(rows: Iterable[termexplore.TermBranch]) -> list[dict]:
    return [{
        "doc_id": row.doc_id,
        "node": row.node,
        "doc": row.doc,
        "path": row.path,
        "origin": row.origin,
        "mandatory": bool(row.mandatory),
    } for row in rows]


def run(index: Index, question: str, llm,
        incumbent: list[termexplore.TermBranch],
        evidence_pool: list[termexplore.TermBranch],
        registry_candidates: list[termexplore.TermBranch],
        target_claim: str, *, cap: int = PRESENTED_MAX,
        pool_cap: int = POOL_MAX) -> tuple[list[termexplore.TermBranch], dict]:
    """Promote coordinates only through exact server-owned span IDs."""
    selected = _dedupe(incumbent, cap=max(1, int(cap)))
    selected_coordinates = {row.coordinate for row in selected}
    registry = _dedupe(
        [row for row in registry_candidates
         if row.coordinate not in selected_coordinates], cap=REGISTRY_MAX)
    pool = _dedupe(
        [*selected, *evidence_pool, *registry],
        cap=max(len(selected), int(pool_cap)))
    available = max(0, int(cap) - len(selected))
    base_meta = {
        "enabled": True,
        "strategy": "verified-span-id-selector",
        "baseline_preserved": True,
        "initial_selected_count": len(selected),
        "initial_observed_count": len(evidence_pool),
        "registry_candidate_count": len(registry),
        "target_claim": str(target_claim or question)[:900],
        "hard_deletes": 0,
        "rejected": [],
        "selected_registry": [],
        "promoted": [],
        "evidence_pool": _pool_rows(pool),
    }
    if not registry or available <= 0:
        return selected, {
            **base_meta,
            "ran": False,
            "status": "unchanged",
            "reason": "no_candidate_or_slot",
            "verified_spans": [],
            "selector_output": None,
            "validation_errors": [],
        }
    if llm is None:
        return selected, {
            **base_meta,
            "ran": False,
            "status": "unavailable",
            "reason": "llm_unavailable",
            "verified_spans": [],
            "selector_output": None,
            "validation_errors": [],
        }

    spans, by_id = _verified_spans(index, registry, question)
    references = _reference_cards(index, selected, question)
    user = (
        f"[원질문]\n{question}\n\n"
        f"[target claim]\n{target_claim or question}\n\n"
        f"[비선택 incumbent 참고 근거 — ID 없음]\n"
        f"{json.dumps(references, ensure_ascii=False)}\n\n"
        f"[선택 가능한 verified span — span_id enum 전용]\n"
        f"{json.dumps(spans, ensure_ascii=False)}"
    )
    output = llm.structured(
        "rag.legalclosure.verified_span_selector",
        _SYSTEM, user, _schema(list(by_id)), max_tokens=OUTPUT_TOKENS_MAX,
        effort=None, model=PRODUCT_MODEL)
    if not isinstance(output, dict):
        output = {"selected_span_ids": [],
                  "remaining_gap": "selector unavailable"}
    accepted, errors = _validate(output.get("selected_span_ids"), by_id)
    accepted_coordinates = {tuple(item["coordinate"]) for item in accepted}
    chosen = [row for row in registry if row.coordinate in accepted_coordinates]
    promoted = chosen[:available]
    selected = [*selected, *promoted]
    return selected, {
        **base_meta,
        "ran": True,
        "status": "complete",
        "reason": "server_verified_span_ids_checked",
        "verified_spans": spans,
        "selector_output": {
            "requested": output,
            "accepted": accepted,
            "remaining_gap": str(output.get("remaining_gap") or "")[:900],
        },
        "validation_errors": errors,
        "selected_registry": _pool_rows(chosen),
        "promoted": _pool_rows(promoted),
    }


__all__ = [
    "POOL_MAX", "PRESENTED_MAX", "REGISTRY_MAX", "SELECTION_MAX",
    "SPAN_CHARS", "run",
]
