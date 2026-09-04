"""Claim-to-citation relevance selector over source-verified candidates.

This experiment-only component keeps the source registry append-only and gives
the model authority only to choose which already verified coordinates may be
presented.  It cannot invent coordinates, delete incumbent evidence, or treat
source validity as legal relevance.
"""

from __future__ import annotations

import json
import re
from typing import Iterable

from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import proof_boundary_feedback as boundary
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
PRESENTED_MAX = 20
POOL_MAX = 48
SELECTION_MAX = 3
INCUMBENT_CARDS_MAX = 12
SOURCE_CHARS = 2_400
INCUMBENT_CHARS = 700
OUTPUT_TOKENS_MAX = 1_800

_SPACE = re.compile(r"\s+")

_SYSTEM = """너는 source registry와 최종 presentation 사이의 claim-citation 관련성 검사자다.

registry 후보는 실제 corpus 좌표와 원문 hash만 검증된 상태다. source가 진짜라는 사실은 질문과
관련 있다는 뜻이 아니다. 원질문의 구체 claim을 직접 뒷받침하거나, 그 claim의 적용에 반드시
필요한 위임·예외·정의·companion 규정인 후보만 선택한다.

다음은 선택하지 않는다.
- 같은 단어만 포함한 다른 제도·다른 주체·다른 법률의 조문
- 신청서·보고서 서식, 부칙, 일반 절차처럼 질문의 claim을 닫지 않는 자료
- 기존 incumbent가 이미 제공하는 근거를 단순 반복하는 자료
- 최종 결론과 연결 경로를 설명할 수 없는 넓은 관련 규정

closed registry menu 밖의 ID를 만들지 않는다. 선택할 때는 후보 원문에 실제로 연속해서 존재하는
짧은 quote를 그대로 복사한다. 관련 후보가 없으면 selections를 빈 배열로 둔다. 전체 답이
완성됐는지 판단하지 말고 각 후보와 target claim의 국소적 근거 관계만 판정한다."""


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "selections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "role": {"type": "string", "enum": [
                            "direct", "companion", "exception", "definition"]},
                        "quote": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["candidate_id", "role", "quote", "reason"],
                    "additionalProperties": False,
                },
            },
            "remaining_gap": {"type": "string"},
        },
        "required": ["selections", "remaining_gap"],
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


def _focused(text: str, question: str, *, cap: int) -> str:
    text = str(text or "")
    if len(text) <= cap:
        return text
    tokens = [token for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", question)
              if len(token) >= 2]
    folded = text.casefold()
    for token in tokens:
        pos = folded.find(token.casefold())
        if pos >= 0:
            return text[max(0, pos - cap // 3):pos + cap * 2 // 3]
    return text[:cap]


def _cards(index: Index, rows: list[termexplore.TermBranch], question: str,
           *, prefix: str, chars: int, cap: int) -> tuple[list[dict], dict]:
    public, by_id = [], {}
    for pos, row in enumerate(rows[:cap], 1):
        cid = f"{prefix}{pos}"
        by_id[cid] = row
        public.append({
            "id": cid,
            "document": row.doc,
            "path": row.path,
            "origin": row.origin,
            "mandatory": bool(row.mandatory),
            "text": _focused(_source(index, row), question, cap=chars),
        })
    return public, by_id


def _normalized(value: object) -> str:
    return _SPACE.sub("", str(value or "")).casefold()


def _validate(index: Index, raw: object, by_id: dict) -> tuple[list[dict], list[str]]:
    accepted: list[dict] = []
    errors: list[str] = []
    seen: set[tuple] = set()
    for pos, item in enumerate(raw if isinstance(raw, list) else (), 1):
        if not isinstance(item, dict):
            errors.append(f"selection_not_object:{pos}")
            continue
        cid = str(item.get("candidate_id") or "")
        row = by_id.get(cid)
        if row is None:
            errors.append(f"candidate_outside_menu:{cid or pos}")
            continue
        quote = str(item.get("quote") or "").strip()
        source = _source(index, row)
        if not quote or _normalized(quote) not in _normalized(source):
            errors.append(f"quote_not_in_source:{cid}")
            continue
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        accepted.append({
            "candidate_id": cid,
            "coordinate": [row.doc_id, row.node],
            "role": str(item.get("role") or "direct"),
            "quote": quote,
            "reason": str(item.get("reason") or "").strip()[:700],
        })
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
    """Select source-verified candidates without deleting incumbent evidence."""
    selected = _dedupe(incumbent, cap=max(1, int(cap)))
    selected_coordinates = {row.coordinate for row in selected}
    registry = _dedupe(
        [row for row in registry_candidates
         if row.coordinate not in selected_coordinates], cap=SELECTION_MAX)
    pool = _dedupe(
        [*selected, *evidence_pool, *registry],
        cap=max(len(selected), int(pool_cap)))
    available = max(0, int(cap) - len(selected))
    base_meta = {
        "enabled": True,
        "strategy": "claim-citation-relevance-selector",
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
            "selector_output": None,
            "validation_errors": [],
        }
    if llm is None:
        return selected, {
            **base_meta,
            "ran": False,
            "status": "unavailable",
            "reason": "llm_unavailable",
            "selector_output": None,
            "validation_errors": [],
        }

    incumbent_cards, _ = _cards(
        index, selected, question, prefix="I", chars=INCUMBENT_CHARS,
        cap=INCUMBENT_CARDS_MAX)
    registry_cards, by_id = _cards(
        index, registry, question, prefix="R", chars=SOURCE_CHARS,
        cap=SELECTION_MAX)
    user = (
        f"[원질문]\n{question}\n\n"
        f"[target claim]\n{target_claim or question}\n\n"
        f"[기존 incumbent 근거]\n"
        f"{json.dumps(incumbent_cards, ensure_ascii=False)}\n\n"
        f"[closed source registry menu]\n"
        f"{json.dumps(registry_cards, ensure_ascii=False)}"
    )
    output = llm.structured(
        "rag.legalclosure.claim_citation_selector",
        _SYSTEM, user, _schema(), max_tokens=OUTPUT_TOKENS_MAX,
        effort=None, model=PRODUCT_MODEL)
    if not isinstance(output, dict):
        output = {"selections": [], "remaining_gap": "selector unavailable"}
    accepted, errors = _validate(index, output.get("selections"), by_id)
    accepted_coordinates = {tuple(item["coordinate"]) for item in accepted}
    chosen = [row for row in registry if row.coordinate in accepted_coordinates]
    promoted = chosen[:available]
    selected = [*selected, *promoted]
    return selected, {
        **base_meta,
        "ran": True,
        "status": "complete",
        "reason": "local_claim_relevance_checked",
        "selector_output": {
            "requested": output,
            "accepted": accepted,
            "remaining_gap": str(output.get("remaining_gap") or "")[:900],
        },
        "validation_errors": errors,
        "selected_registry": _pool_rows(chosen),
        "promoted": _pool_rows(promoted),
    }


__all__ = ["POOL_MAX", "PRESENTED_MAX", "SELECTION_MAX", "run"]
