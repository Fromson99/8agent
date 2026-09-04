"""Provider-compatible server-verified span ID selector.

ADR-0072 preserves ADR-0071's authority boundary but removes JSON-schema
keywords rejected by the provider.  Selection count and deduplication remain
deterministically enforced after structured output validation.
"""

from __future__ import annotations

import json

from lawrag.core.rag import verified_span_selector as base
from lawrag.core.rag.index import Index


PRODUCT_MODEL = base.PRODUCT_MODEL
PRESENTED_MAX = base.PRESENTED_MAX
POOL_MAX = base.POOL_MAX
REGISTRY_MAX = base.REGISTRY_MAX
SELECTION_MAX = base.SELECTION_MAX
OUTPUT_TOKENS_MAX = base.OUTPUT_TOKENS_MAX


def _schema(span_ids: list[str]) -> dict:
    """Use only provider-supported array items enum constraints."""
    return {
        "type": "object",
        "properties": {
            "selected_span_ids": {
                "type": "array",
                "items": {"type": "string", "enum": list(span_ids)},
            },
            "remaining_gap": {"type": "string"},
        },
        "required": ["selected_span_ids", "remaining_gap"],
        "additionalProperties": False,
    }


def run(index: Index, question: str, llm, incumbent: list,
        evidence_pool: list, registry_candidates: list, target_claim: str,
        *, cap: int = PRESENTED_MAX, pool_cap: int = POOL_MAX) -> tuple[list, dict]:
    selected = base._dedupe(incumbent, cap=max(1, int(cap)))
    selected_coordinates = {row.coordinate for row in selected}
    registry = base._dedupe(
        [row for row in registry_candidates
         if row.coordinate not in selected_coordinates], cap=REGISTRY_MAX)
    pool = base._dedupe(
        [*selected, *evidence_pool, *registry],
        cap=max(len(selected), int(pool_cap)))
    available = max(0, int(cap) - len(selected))
    base_meta = {
        "enabled": True,
        "strategy": "provider-compatible-verified-span-id-selector",
        "baseline_preserved": True,
        "initial_selected_count": len(selected),
        "initial_observed_count": len(evidence_pool),
        "registry_candidate_count": len(registry),
        "target_claim": str(target_claim or question)[:900],
        "hard_deletes": 0,
        "rejected": [],
        "selected_registry": [],
        "promoted": [],
        "evidence_pool": base._pool_rows(pool),
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

    spans, by_id = base._verified_spans(index, registry, question)
    references = base._reference_cards(index, selected, question)
    user = (
        f"[원질문]\n{question}\n\n"
        f"[target claim]\n{target_claim or question}\n\n"
        f"[비선택 incumbent 참고 근거 — ID 없음]\n"
        f"{json.dumps(references, ensure_ascii=False)}\n\n"
        f"[선택 가능한 verified span — span_id enum 전용]\n"
        f"{json.dumps(spans, ensure_ascii=False)}"
    )
    output = llm.structured(
        "rag.legalclosure.provider_compatible_span_selector",
        base._SYSTEM, user, _schema(list(by_id)),
        max_tokens=OUTPUT_TOKENS_MAX, effort=None, model=PRODUCT_MODEL)
    if not isinstance(output, dict):
        output = {"selected_span_ids": [],
                  "remaining_gap": "selector unavailable"}
    accepted, errors = base._validate(output.get("selected_span_ids"), by_id)
    accepted_coordinates = {tuple(item["coordinate"]) for item in accepted}
    chosen = [row for row in registry if row.coordinate in accepted_coordinates]
    promoted = chosen[:available]
    selected = [*selected, *promoted]
    return selected, {
        **base_meta,
        "ran": True,
        "status": "complete",
        "reason": "provider_compatible_server_span_ids_checked",
        "verified_spans": spans,
        "selector_output": {
            "requested": output,
            "accepted": accepted,
            "remaining_gap": str(output.get("remaining_gap") or "")[:900],
        },
        "validation_errors": errors,
        "selected_registry": base._pool_rows(chosen),
        "promoted": base._pool_rows(promoted),
    }


__all__ = ["POOL_MAX", "PRESENTED_MAX", "SELECTION_MAX", "run"]
