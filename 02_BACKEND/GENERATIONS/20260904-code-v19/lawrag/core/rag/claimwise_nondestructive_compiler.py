"""Claim-local, non-destructive legal answer compiler for ADR-0121.

This research-only adapter treats an inherited answer as an immutable floor.
The model may audit exact answer spans against a closed menu of already
validated proposition quotes.  Only ``CONDITIONAL`` or ``CONFLICTED`` claims
may be replaced, and replacements are applied deterministically to the exact
target span.  ``MISSING`` never blocks or changes the answer; it only remains
diagnostic input for targeted retrieval.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import time
from typing import Any, Mapping, Sequence

from lawrag.runtime import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_proposition_compiler import EvidenceSpan, PRODUCT_MODEL


PROFILE = "claimwise-nondestructive-v2"
AUDIT_MAX_TOKENS = 5000
MERGE_MAX_TOKENS = 4000
CLAIM_CAP = 12

CLAIM_STATES = ("SUPPORTED", "CONDITIONAL", "MISSING", "CONFLICTED")

_BASELINE_STAGES = (
    ("question-source", "source", ()),
    ("inherited-parent-evidence", "retrieve", ("question-source",)),
    ("compiled-evidence-present", "present", ("inherited-parent-evidence",)),
)
_CANDIDATE_STAGES = (
    ("question-source", "source", ()),
    ("inherited-parent-evidence", "retrieve", ("question-source",)),
    ("claimwise-proposition-compile", "select", ("inherited-parent-evidence",)),
    ("baseline-claim-audit", "filter", ("claimwise-proposition-compile",)),
    ("nondestructive-answer-merge", "select", ("baseline-claim-audit",)),
    ("compiled-evidence-present", "present", ("nondestructive-answer-merge",)),
)


CLAIM_AUDIT_SYSTEM = """너는 최종 답변을 새로 쓰지 않는 법률명제 감사기다.
baseline_answer의 연속 exact span만 claim으로 선택한다. 서버가 준 proposition_menu의
evidence_id와 source_quote만 근거로 사용할 수 있다.

상태는 다음과 같다.
- SUPPORTED: exact quote가 해당 답변 명제를 직접 지지한다.
- CONDITIONAL: 명제는 quote에 적힌 조건·예외·범위 아래에서만 성립한다.
- CONFLICTED: 명제가 quote와 직접 충돌한다.
- MISSING: 메뉴만으로 확인할 수 없다.

SUPPORTED, CONDITIONAL, CONFLICTED에는 실제 grounds를 넣고 MISSING에는 grounds를 넣지
않는다. 질문에 없는 사실, quote에 없는 법률효과, 새로운 evidence ID를 만들지 않는다.
모호하면 MISSING으로 둔다. 답변 전체의 가능·불가능을 판정하지 않는다."""


PATCH_MERGE_SYSTEM = """너는 baseline 법률답변의 국소 patch 작성기다.
서버가 허용한 CONDITIONAL 또는 CONFLICTED claim만 대상으로 replacement_text를 작성한다.
replacement_text에는 해당 claim의 source_quote를 원문 그대로 최소 하나 포함해야 한다.
다른 문장, MISSING claim, 새로운 사실·조문·법률효과를 수정하거나 추가하지 않는다.
전체 답변이 아니라 patch 배열만 반환한다. 확실한 개선이 아니면 patch를 반환하지 않는다."""


@dataclass(frozen=True)
class ClaimAudit:
    claim_id: str
    answer_span: str
    state: str
    grounds: tuple[dict[str, str], ...]

    def public(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "answer_span": self.answer_span,
            "state": self.state,
            "grounds": [dict(row) for row in self.grounds],
        }


def stage_specs(arm_id: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    return _BASELINE_STAGES if arm_id == "baseline" else _CANDIDATE_STAGES


def _proposition_menu(
    evidence: Sequence[EvidenceSpan], packet: Mapping[str, Any],
) -> list[dict[str, str]]:
    evidence_by_id = {row.evidence_id: row for row in evidence}
    seen: set[tuple[str, str]] = set()
    menu: list[dict[str, str]] = []
    for raw in packet.get("claims") or packet.get("units") or ():
        if not isinstance(raw, Mapping):
            continue
        evidence_id = str(raw.get("evidence_id") or "")
        quote = str(raw.get("quote") or raw.get("proposition") or "")
        item = evidence_by_id.get(evidence_id)
        key = (evidence_id, quote)
        if item is None or not quote or quote not in item.text or key in seen:
            continue
        seen.add(key)
        menu.append({
            "evidence_id": evidence_id,
            "document": item.document,
            "path": item.path,
            "source_quote": quote,
            "role": str(raw.get("role") or ""),
        })
    return menu


def _audit_schema(evidence_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "answer_span": {"type": "string"},
                        "state": {"type": "string", "enum": list(CLAIM_STATES)},
                        "grounds": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "evidence_id": {
                                        "type": "string", "enum": list(evidence_ids),
                                    },
                                    "source_quote": {"type": "string"},
                                },
                                "required": ["evidence_id", "source_quote"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["claim_id", "answer_span", "state", "grounds"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }


def _sanitize_audits(
    raw: object,
    baseline_text: str,
    menu: Sequence[Mapping[str, str]],
) -> tuple[list[ClaimAudit], dict[str, list[str]]]:
    quote_by_evidence: dict[str, set[str]] = {}
    for row in menu:
        quote_by_evidence.setdefault(str(row["evidence_id"]), set()).add(
            str(row["source_quote"])
        )
    violations = {
        "answer_span": [],
        "closed_evidence": [],
        "exact_quote": [],
        "state_ground": [],
        "overlap": [],
    }
    rows = list(raw.get("claims") or ()) if isinstance(raw, Mapping) else []
    accepted: list[ClaimAudit] = []
    used_ids: set[str] = set()
    occupied: list[tuple[int, int]] = []
    for position, row in enumerate(rows[:CLAIM_CAP], 1):
        if not isinstance(row, Mapping):
            violations["answer_span"].append(f"row-{position}")
            continue
        claim_id = str(row.get("claim_id") or f"row-{position}")
        if claim_id in used_ids:
            violations["answer_span"].append(claim_id)
            continue
        answer_span = str(row.get("answer_span") or "")
        start = baseline_text.find(answer_span) if answer_span else -1
        if start < 0:
            violations["answer_span"].append(claim_id)
            continue
        end = start + len(answer_span)
        if any(start < prior_end and prior_start < end for prior_start, prior_end in occupied):
            violations["overlap"].append(claim_id)
            continue
        state = str(row.get("state") or "")
        if state not in CLAIM_STATES:
            violations["state_ground"].append(claim_id)
            continue
        grounds: list[dict[str, str]] = []
        invalid_ground = False
        for ground in row.get("grounds") or ():
            if not isinstance(ground, Mapping):
                invalid_ground = True
                continue
            evidence_id = str(ground.get("evidence_id") or "")
            quote = str(ground.get("source_quote") or "")
            if evidence_id not in quote_by_evidence:
                violations["closed_evidence"].append(claim_id)
                invalid_ground = True
                continue
            if quote not in quote_by_evidence[evidence_id]:
                violations["exact_quote"].append(claim_id)
                invalid_ground = True
                continue
            grounds.append({"evidence_id": evidence_id, "source_quote": quote})
        if invalid_ground:
            continue
        if state == "MISSING" and grounds:
            violations["state_ground"].append(claim_id)
            continue
        if state != "MISSING" and not grounds:
            violations["state_ground"].append(claim_id)
            continue
        used_ids.add(claim_id)
        occupied.append((start, end))
        accepted.append(ClaimAudit(claim_id, answer_span, state, tuple(grounds)))
    for key in violations:
        violations[key] = sorted(set(violations[key]))
    return accepted, violations


def _patch_schema(claim_ids: Sequence[str], evidence_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "patches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "enum": list(claim_ids)},
                        "replacement_text": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(evidence_ids)},
                        },
                    },
                    "required": ["claim_id", "replacement_text", "evidence_ids"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["patches"],
        "additionalProperties": False,
    }


def _sanitize_patches(
    raw: object, audits: Sequence[ClaimAudit], baseline_text: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    allowed = {
        row.claim_id: row for row in audits
        if row.state in {"CONDITIONAL", "CONFLICTED"}
    }
    violations = {"patch_target": [], "replacement_ground": []}
    rows = list(raw.get("patches") or ()) if isinstance(raw, Mapping) else []
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, row in enumerate(rows, 1):
        if not isinstance(row, Mapping):
            violations["patch_target"].append(f"row-{position}")
            continue
        claim_id = str(row.get("claim_id") or f"row-{position}")
        audit = allowed.get(claim_id)
        if audit is None or claim_id in seen:
            violations["patch_target"].append(claim_id)
            continue
        replacement = str(row.get("replacement_text") or "").strip()
        allowed_ids = {ground["evidence_id"] for ground in audit.grounds}
        used_ids = [str(value) for value in row.get("evidence_ids") or ()]
        quotes = [ground["source_quote"] for ground in audit.grounds]
        if (
            not replacement
            or len(replacement) > 2000
            or not used_ids
            or any(value not in allowed_ids for value in used_ids)
            or not any(quote in replacement for quote in quotes)
        ):
            violations["replacement_ground"].append(claim_id)
            continue
        start = baseline_text.find(audit.answer_span)
        if start < 0:
            violations["patch_target"].append(claim_id)
            continue
        seen.add(claim_id)
        accepted.append({
            "claim_id": claim_id,
            "start": start,
            "end": start + len(audit.answer_span),
            "replacement_text": replacement,
            "evidence_ids": list(dict.fromkeys(used_ids)),
        })
    accepted.sort(key=lambda row: int(row["start"]), reverse=True)
    for key in violations:
        violations[key] = sorted(set(violations[key]))
    return accepted, violations


def _apply_patches(baseline_text: str, patches: Sequence[Mapping[str, Any]]) -> str:
    answer = baseline_text
    for row in patches:
        start, end = int(row["start"]), int(row["end"])
        answer = answer[:start] + str(row["replacement_text"]) + answer[end:]
    return answer


def compile_claimwise_answer(
    question: str,
    baseline_answer: Mapping[str, Any],
    evidence: Sequence[EvidenceSpan],
    compiler_packet: Mapping[str, Any],
    *,
    llm: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Audit and patch exact baseline claims without a question-level gate."""

    started = time.perf_counter()
    baseline_payload = deepcopy(dict(baseline_answer))
    baseline_text = str(baseline_payload.get("answer") or "")
    menu = _proposition_menu(evidence, compiler_packet)
    audit_raw: object = {"claims": []}
    audit_ms = 0.0
    if baseline_text and menu and llm is not None:
        audit_started = time.perf_counter()
        audit_raw = llm.structured(
            "rag.claimwise_nondestructive.claim_audit",
            CLAIM_AUDIT_SYSTEM,
            json.dumps({
                "question": question,
                "baseline_answer": baseline_text,
                "proposition_menu": menu,
                "missing_coverage": list(compiler_packet.get("missing") or ()),
                "instruction": "MISSING은 답변 전체를 차단하지 않는다.",
            }, ensure_ascii=False, separators=(",", ":")),
            _audit_schema([row["evidence_id"] for row in menu]),
            max_tokens=AUDIT_MAX_TOKENS,
            effort="low",
            model=PRODUCT_MODEL,
        )
        audit_ms = round((time.perf_counter() - audit_started) * 1000, 3)
    audits, audit_violations = _sanitize_audits(audit_raw, baseline_text, menu)
    patchable = [
        row for row in audits if row.state in {"CONDITIONAL", "CONFLICTED"}
    ]
    patch_raw: object = {"patches": []}
    merge_ms = 0.0
    if patchable and llm is not None:
        merge_started = time.perf_counter()
        evidence_ids = list(dict.fromkeys(
            ground["evidence_id"] for row in patchable for ground in row.grounds
        ))
        patch_raw = llm.structured(
            "rag.claimwise_nondestructive.answer_merge",
            PATCH_MERGE_SYSTEM,
            json.dumps({
                "question": question,
                "baseline_answer": baseline_text,
                "patchable_claims": [row.public() for row in patchable],
            }, ensure_ascii=False, separators=(",", ":")),
            _patch_schema([row.claim_id for row in patchable], evidence_ids),
            max_tokens=MERGE_MAX_TOKENS,
            effort="low",
            model=PRODUCT_MODEL,
        )
        merge_ms = round((time.perf_counter() - merge_started) * 1000, 3)
    patches, patch_violations = _sanitize_patches(patch_raw, audits, baseline_text)
    answer_text = _apply_patches(baseline_text, patches)
    output = deepcopy(baseline_payload)
    output["answer"] = answer_text
    output["answerable"] = bool(baseline_payload.get("answerable"))
    output["gate_violation"] = False
    output["error"] = ""
    if patches and output.get("conclusion_strength") == "DIRECT":
        output["conclusion_strength"] = "QUALIFIED"

    validation = {
        "answer_span_violations": audit_violations["answer_span"],
        "closed_evidence_violations": audit_violations["closed_evidence"],
        "exact_quote_violations": audit_violations["exact_quote"],
        "state_ground_violations": audit_violations["state_ground"],
        "overlap_violations": audit_violations["overlap"],
        "patch_target_violations": patch_violations["patch_target"],
        "replacement_ground_violations": patch_violations["replacement_ground"],
        "untouched_text_violations": [],
        "global_block_violations": [],
    }
    meta = {
        "enabled": True,
        "profile": PROFILE,
        "baseline_preserved_exactly": answer_text == baseline_text,
        "claim_count": len(audits),
        "supported_count": sum(row.state == "SUPPORTED" for row in audits),
        "conditional_count": sum(row.state == "CONDITIONAL" for row in audits),
        "missing_count": sum(row.state == "MISSING" for row in audits),
        "conflicted_count": sum(row.state == "CONFLICTED" for row in audits),
        "patch_count": len(patches),
        "global_block_count": 0,
        "audits": [row.public() for row in audits],
        "patches": deepcopy(patches),
        "targeted_search_plan": list(compiler_packet.get("search_plan") or ()),
        "audit_receipt": {"raw_output": audit_raw, "elapsed_ms": audit_ms},
        "merge_receipt": {"raw_output": patch_raw, "elapsed_ms": merge_ms},
        "validation": validation,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return output, meta


def capture_stages(
    index: Index, case_id: str, arm_id: str, sections: Sequence[Any],
) -> dict[str, Any]:
    coordinates = [(section.doc_id, int(section.node)) for section in sections]
    recorder = stage_ledger.StageLedgerRecorder(
        case_id, arm_id, stage_ledger.index_article_root_canonicalizer(index)
    )
    for stage_id, kind, parents in stage_specs(arm_id):
        after = [] if stage_id == "question-source" else coordinates
        recorder.record_stage(stage_id, kind, after, parent_stage_ids=parents)
    return recorder.capture()


__all__ = [
    "PROFILE",
    "capture_stages",
    "compile_claimwise_answer",
    "stage_specs",
]
