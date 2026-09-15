"""Platform-owned ADR arm을 운영 MAIN RAG 배선에 원자적으로 승격하는 원장.

승격은 코드를 자동 생성하거나 실험 결과를 임의 채택하지 않는다. Accepted·decision-eligible
ADR arm과 검증 receipt를 hash로 고정한 plan만 MAIN manifest의 새 generation으로 적용한다.
실제 런타임 변화는 등록된 engine switch를 통해서만 일어나므로 모든 code artifact는
rollback 가능한 guard switch를 가져야 한다.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any, Iterable, Mapping

from lawrag.core.rag.index import store_path


PIPELINE_SCHEMA = "main-rag-pipeline-v1"
PLAN_SCHEMA = "main-rag-promotion-plan-v1"
RECEIPT_SCHEMA = "main-rag-promotion-receipt-v2"
LEGACY_RECEIPT_SCHEMA = "main-rag-promotion-receipt-v1"
TRANSITION_CHAIN_SCHEMA = "main-rag-transition-chain-v1"
PIPELINE_ID = "legalclosure-v2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(data: Any) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint(data: Any) -> str:
    return hashlib.sha256(_canonical(data)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_path() -> Path:
    return Path(os.environ.get(
        "RAG_MAIN_PIPELINE_MANIFEST", store_path().parent / "main" / "pipeline.json"))


def receipts_path() -> Path:
    return Path(os.environ.get(
        "RAG_MAIN_PROMOTION_RECEIPTS",
        manifest_path().with_name("promotion_receipts.jsonl")))


def default_state() -> dict[str, Any]:
    return {
        "schema_version": PIPELINE_SCHEMA,
        "pipeline_id": PIPELINE_ID,
        "runtime_profile": PIPELINE_ID,
        "generation": 0,
        "active_promotion_id": None,
        "active_promotions": [],
        "switches": {},
        "code_artifacts": [],
        "updated_at": None,
    }


def historical_default_state() -> dict[str, Any]:
    """Return the exact pre-runtime-profile generation-zero MAIN root.

    This is a frozen compatibility root, not a template for new state.  Old
    state and receipt bytes remain unchanged; only an in-memory transition
    chain may start here.
    """

    state = default_state()
    del state["runtime_profile"]
    return state


def effective_runtime_profile(state: Mapping[str, Any]) -> Any:
    """Interpret the one historically omitted field without mutating state."""

    return state["runtime_profile"] if "runtime_profile" in state else PIPELINE_ID


def validate_state(state: Mapping[str, Any]) -> list[str]:
    """Validate one MAIN state, including the canonical generation-zero root.

    Generation zero is the sole state that has no promotion transition proof.
    It has the modern canonical representation and one frozen historical
    representation that predates ``runtime_profile``.  Any other change must
    advance the generation and carry the sealed plan/receipt chain.
    """

    errors: list[str] = []
    state_fields = frozenset(state)
    modern_fields = set(default_state())
    historical_fields = set(historical_default_state())
    if state_fields not in {frozenset(modern_fields), frozenset(historical_fields)}:
        errors.append("MAIN state fields are not exact")
    if state.get("schema_version") != PIPELINE_SCHEMA:
        errors.append(f"schema_version must be {PIPELINE_SCHEMA}")
    if state.get("pipeline_id") != PIPELINE_ID:
        errors.append(f"pipeline_id must be {PIPELINE_ID}")
    runtime_profile = effective_runtime_profile(state)
    if (
        not isinstance(runtime_profile, str)
        or not runtime_profile
        or runtime_profile != runtime_profile.strip()
    ):
        errors.append("runtime_profile must be exact non-empty text")
    generation = state.get("generation")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 0
    ):
        errors.append("generation must be a non-negative integer")
    if not isinstance(state.get("active_promotions"), list):
        errors.append("active_promotions must be a list")
    switches = state.get("switches")
    if not isinstance(switches, dict):
        errors.append("switches must be an object")
    elif any(
        not isinstance(key, str)
        or not key
        or key != key.strip()
        or not isinstance(value, bool)
        for key, value in switches.items()
    ):
        errors.append("switches must map exact non-empty names to booleans")
    if not isinstance(state.get("code_artifacts"), list):
        errors.append("code_artifacts must be a list")
    active_id = state.get("active_promotion_id")
    if active_id is not None and (
        not isinstance(active_id, str)
        or not active_id
        or active_id != active_id.strip()
    ):
        errors.append("active_promotion_id must be null or exact non-empty text")
    updated_at = state.get("updated_at")
    if updated_at is not None and (
        not isinstance(updated_at, str)
        or not updated_at
        or updated_at != updated_at.strip()
    ):
        errors.append("updated_at must be null or exact non-empty text")
    if generation == 0 and dict(state) not in (
        default_state(), historical_default_state()
    ):
        errors.append("generation-zero MAIN state must equal a canonical default")
    return errors


def _validate_state(state: Mapping[str, Any]) -> list[str]:
    """Backward-compatible internal alias for the public sealed validator."""

    return validate_state(state)


def load_state() -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        return default_state()
    state = json.loads(path.read_text("utf-8"))
    errors = _validate_state(state)
    if errors:
        raise ValueError("invalid MAIN pipeline manifest: " + "; ".join(errors))
    return state


def validate_apply_receipt(
    receipt: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    """Validate that standalone apply-receipt bytes prove this MAIN state.

    Release activation hashes the receipt file.  This function additionally
    proves the legal meaning of those bytes: one exact transition to the
    currently active promotion, rather than an arbitrary file with the hash a
    manifest happened to claim.
    """

    errors = list(_validate_state(state))
    expected_fields = {
        "schema_version",
        "receipt_id",
        "action",
        "promotion_id",
        "at",
        "actor",
        "approval_note",
        "plan_sha256",
        "promotion_plan",
        "source",
        "before_state",
        "before_state_sha256",
        "after_state_sha256",
    }
    legacy_bridge_fields = expected_fields | {
        "legacy_receipt", "legacy_receipt_sha256"
    }
    receipt_fields = set(receipt)
    if receipt_fields not in (expected_fields, legacy_bridge_fields):
        errors.append("apply receipt fields are not exact")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        errors.append(f"receipt schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("action") != "apply":
        errors.append("MAIN runtime receipt must be an apply receipt")
    if receipt_fields == legacy_bridge_fields:
        legacy = receipt.get("legacy_receipt")
        legacy_fields = expected_fields - {"promotion_plan"}
        if (
            not isinstance(legacy, dict)
            or set(legacy) != legacy_fields
            or legacy.get("schema_version") != LEGACY_RECEIPT_SCHEMA
            or legacy.get("action") != "apply"
        ):
            errors.append("normalized legacy receipt evidence is invalid")
            legacy = {}
        legacy_sha = receipt.get("legacy_receipt_sha256")
        if legacy_sha != fingerprint(legacy):
            errors.append("normalized legacy receipt evidence hash mismatch")
        for field in legacy_fields - {"schema_version"}:
            if receipt.get(field) != legacy.get(field):
                errors.append(
                    f"normalized legacy receipt changed historical field: {field}"
                )
    elif "legacy_receipt" in receipt or "legacy_receipt_sha256" in receipt:
        errors.append("legacy receipt evidence must be complete")
    for field in ("receipt_id", "promotion_id", "at", "actor", "approval_note"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            errors.append(f"receipt {field} must be exact non-empty text")
    for field in ("plan_sha256", "before_state_sha256", "after_state_sha256"):
        value = receipt.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            errors.append(f"receipt {field} must be lowercase SHA-256")

    promotion_plan = receipt.get("promotion_plan")
    if not isinstance(promotion_plan, dict):
        errors.append("apply receipt must embed its exact promotion plan")
        promotion_plan = {}
    if receipt.get("plan_sha256") != fingerprint(promotion_plan):
        errors.append("embedded promotion plan hash mismatch")

    before = receipt.get("before_state")
    if not isinstance(before, dict):
        errors.append("receipt before_state must be an object")
        before = default_state()
    else:
        errors.extend(f"before_state: {item}" for item in _validate_state(before))
    if receipt.get("before_state_sha256") != fingerprint(before):
        errors.append("receipt before_state hash mismatch")
    if receipt.get("after_state_sha256") != fingerprint(state):
        errors.append("receipt after_state hash mismatch")
    before_generation = before.get("generation")
    state_generation = state.get("generation")
    if (
        isinstance(before_generation, bool)
        or not isinstance(before_generation, int)
        or isinstance(state_generation, bool)
        or not isinstance(state_generation, int)
        or state_generation != before_generation + 1
    ):
        errors.append("receipt does not prove one MAIN generation transition")

    promotion_id = receipt.get("promotion_id")
    if state.get("active_promotion_id") != promotion_id:
        errors.append("receipt promotion is not the active MAIN promotion")
    before_promotions = before.get("active_promotions")
    after_promotions = state.get("active_promotions")
    if not isinstance(before_promotions, list) or not isinstance(after_promotions, list):
        errors.append("receipt MAIN promotion histories are invalid")
        promoted: dict[str, Any] = {}
    elif (
        len(after_promotions) != len(before_promotions) + 1
        or after_promotions[:-1] != before_promotions
        or not isinstance(after_promotions[-1], dict)
    ):
        errors.append("receipt does not prove an append-only MAIN promotion")
        promoted = {}
    else:
        promoted = after_promotions[-1]
    if promoted.get("promotion_id") != promotion_id:
        errors.append("receipt promotion does not match appended MAIN row")
    if receipt.get("at") != promoted.get("applied_at"):
        errors.append("receipt timestamp does not match appended MAIN row")
    if receipt.get("actor") != promoted.get("applied_by"):
        errors.append("receipt actor does not match appended MAIN row")
    if state.get("updated_at") != receipt.get("at"):
        errors.append("MAIN updated_at does not match receipt")

    source = receipt.get("source")
    expected_source_fields = {
        "adr_id",
        "experiment_id",
        "arm_id",
        "manifest_path",
        "manifest_sha256",
    }
    if not isinstance(source, dict) or set(source) != expected_source_fields:
        errors.append("receipt source fields are invalid")
        source = {}
    for field in ("adr_id", "experiment_id", "arm_id", "manifest_path"):
        value = source.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            errors.append(f"receipt source {field} must be exact non-empty text")
    manifest_sha = source.get("manifest_sha256")
    if (
        not isinstance(manifest_sha, str)
        or len(manifest_sha) != 64
        or any(character not in "0123456789abcdef" for character in manifest_sha)
    ):
        errors.append("receipt source manifest_sha256 must be lowercase SHA-256")
    for source_field, promotion_field in (
        ("adr_id", "adr_id"),
        ("experiment_id", "experiment_id"),
        ("arm_id", "arm_id"),
        ("manifest_sha256", "source_manifest_sha256"),
    ):
        if source.get(source_field) != promoted.get(promotion_field):
            errors.append(
                f"receipt source {source_field} does not match appended MAIN row"
            )
    if any(
        isinstance(row, dict) and row.get("promotion_id") == promotion_id
        for row in before.get("active_promotions", [])
    ):
        errors.append("receipt promotion already existed before the transition")
    return errors


def validate_rollback_receipt(
    receipt: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    """Validate a self-contained rollback transition to ``state``.

    A rollback is a new MAIN generation, not a return to an old generation.
    The receipt therefore carries both the immediately preceding state and the
    complete apply receipt being reversed.  A release can prove the transition
    without consulting a mutable receipt ledger.
    """

    errors = list(_validate_state(state))
    expected_fields = {
        "schema_version",
        "receipt_id",
        "action",
        "promotion_id",
        "at",
        "actor",
        "note",
        "before_state",
        "before_state_sha256",
        "after_state_sha256",
        "rolled_back_apply_receipt",
        "rolled_back_apply_receipt_sha256",
    }
    if set(receipt) != expected_fields:
        errors.append("rollback receipt fields are not exact")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        errors.append(f"receipt schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("action") != "rollback":
        errors.append("MAIN runtime receipt must be a rollback receipt")
    for field in ("receipt_id", "promotion_id", "at", "actor", "note"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            errors.append(f"receipt {field} must be exact non-empty text")
    for field in (
        "before_state_sha256",
        "after_state_sha256",
        "rolled_back_apply_receipt_sha256",
    ):
        value = receipt.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            errors.append(f"receipt {field} must be lowercase SHA-256")

    before = receipt.get("before_state")
    if not isinstance(before, dict):
        errors.append("rollback before_state must be an object")
        before = default_state()
    else:
        errors.extend(f"before_state: {item}" for item in _validate_state(before))
    if receipt.get("before_state_sha256") != fingerprint(before):
        errors.append("rollback before_state hash mismatch")
    if receipt.get("after_state_sha256") != fingerprint(state):
        errors.append("rollback after_state hash mismatch")
    before_generation = before.get("generation")
    state_generation = state.get("generation")
    if (
        isinstance(before_generation, bool)
        or not isinstance(before_generation, int)
        or isinstance(state_generation, bool)
        or not isinstance(state_generation, int)
        or state_generation != before_generation + 1
    ):
        errors.append("rollback does not prove one MAIN generation transition")

    apply_receipt = receipt.get("rolled_back_apply_receipt")
    if not isinstance(apply_receipt, dict):
        errors.append("rollback must embed the reversed apply receipt")
        apply_receipt = {}
    if receipt.get("rolled_back_apply_receipt_sha256") != fingerprint(apply_receipt):
        errors.append("embedded apply receipt hash mismatch")
    # A previously restored promotion has a newer generation/timestamp than
    # its original apply.  Reconstruct the original apply state from the
    # current semantic state, then verify the embedded receipt against that
    # exact historical identity.  This supports A→B→rollback B→rollback A
    # without treating generation counters as business-state mutations.
    apply_before = apply_receipt.get("before_state")
    reconstructed_apply_state = deepcopy(before)
    if isinstance(apply_before, dict):
        apply_before_generation = apply_before.get("generation")
        if (
            isinstance(apply_before_generation, bool)
            or not isinstance(apply_before_generation, int)
        ):
            errors.append("embedded apply receipt has an invalid prior generation")
        else:
            reconstructed_apply_state["generation"] = apply_before_generation + 1
            reconstructed_apply_state["updated_at"] = apply_receipt.get("at")
            errors.extend(
                f"rolled_back_apply_receipt: {item}"
                for item in validate_apply_receipt(
                    apply_receipt, reconstructed_apply_state
                )
            )
            semantic_before = {
                key: value for key, value in before.items()
                if key not in {"generation", "updated_at"}
            }
            semantic_applied = {
                key: value for key, value in reconstructed_apply_state.items()
                if key not in {"generation", "updated_at"}
            }
            if semantic_before != semantic_applied:
                errors.append(
                    "rollback input is not semantically equal to the applied MAIN state"
                )
    if receipt.get("promotion_id") != apply_receipt.get("promotion_id"):
        errors.append("rollback promotion does not match embedded apply receipt")

    original = apply_receipt.get("before_state")
    if not isinstance(original, dict):
        errors.append("embedded apply receipt has no original MAIN state")
    else:
        expected_state = deepcopy(original)
        expected_state["generation"] = (
            before_generation + 1
            if isinstance(before_generation, int)
            and not isinstance(before_generation, bool)
            else -1
        )
        expected_state["updated_at"] = receipt.get("at")
        if state != expected_state:
            errors.append("rollback state is not the exact restored MAIN state")
    if state.get("updated_at") != receipt.get("at"):
        errors.append("rollback MAIN updated_at does not match receipt")
    return errors


def validate_transition_receipt(
    receipt: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    """Validate the exact apply or rollback transition that produced ``state``."""

    action = receipt.get("action")
    if action == "apply":
        return validate_apply_receipt(receipt, state)
    if action == "rollback":
        return validate_rollback_receipt(receipt, state)
    return ["MAIN runtime receipt action must be apply or rollback"]


def transition_chain_tip(chain: Mapping[str, Any]) -> dict[str, Any]:
    """Return the chain tip without consulting the mutable authoring ledger."""

    rows = chain.get("transitions")
    if not isinstance(rows, list) or not rows or not isinstance(rows[-1], dict):
        raise ValueError("MAIN transition chain has no receipt tip")
    return deepcopy(rows[-1])


def normalize_legacy_apply_receipt(
    receipt: Mapping[str, Any],
    promotion_plan: Mapping[str, Any],
    after_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert one exact v1 apply receipt to a self-contained v2 receipt.

    The operation is authoring-only and purely in memory.  It neither rewrites
    the historical JSONL ledger nor adds fields to the historical MAIN state.
    The supplied plan must be the unique externally selected object whose
    canonical hash was already sealed into the v1 receipt.
    """

    legacy_fields = {
        "schema_version", "receipt_id", "action", "promotion_id", "at",
        "actor", "approval_note", "plan_sha256", "source", "before_state",
        "before_state_sha256", "after_state_sha256",
    }
    if set(receipt) != legacy_fields:
        raise ValueError("legacy MAIN apply receipt fields are not exact")
    if receipt.get("schema_version") != LEGACY_RECEIPT_SCHEMA:
        raise ValueError(f"legacy receipt schema must be {LEGACY_RECEIPT_SCHEMA}")
    if receipt.get("action") != "apply":
        raise ValueError("only legacy apply receipts can be normalized")
    plan = deepcopy(dict(promotion_plan))
    if fingerprint(plan) != receipt.get("plan_sha256"):
        raise ValueError("legacy receipt does not hash-match the supplied plan")
    normalized = deepcopy(dict(receipt))
    normalized["schema_version"] = RECEIPT_SCHEMA
    normalized["promotion_plan"] = plan
    normalized["legacy_receipt"] = deepcopy(dict(receipt))
    normalized["legacy_receipt_sha256"] = fingerprint(dict(receipt))
    state = deepcopy(dict(after_state))
    errors = validate_apply_receipt(normalized, state)
    errors.extend(validate_runtime_promotion_plan(plan, normalized, state))
    if errors:
        raise ValueError("invalid normalized legacy receipt: " + "; ".join(errors))
    return normalized


def normalize_transition_receipts(
    receipts: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    *,
    legacy_promotion_plans: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return strict v2 rows, resolving every v1 row by exact plan hash.

    Plan candidates are explicit inputs.  No environment, filename convention,
    directory scan, or first-match fallback participates in authority.  A
    duplicate candidate hash is rejected even when its decoded JSON is equal,
    keeping the authoring selection auditable and unambiguous.
    """

    rows = [deepcopy(dict(row)) for row in receipts]
    plans_by_hash: dict[str, dict[str, Any]] = {}
    for raw_plan in legacy_promotion_plans:
        plan = deepcopy(dict(raw_plan))
        digest = fingerprint(plan)
        if digest in plans_by_hash:
            raise ValueError(f"duplicate legacy promotion plan candidate: {digest}")
        plans_by_hash[digest] = plan
    normalized: list[dict[str, Any]] = []
    used_plan_hashes: set[str] = set()
    for index, receipt in enumerate(rows):
        schema = receipt.get("schema_version")
        if index + 1 < len(rows):
            next_before = rows[index + 1].get("before_state")
            if not isinstance(next_before, Mapping):
                raise ValueError(f"transition[{index + 1}] has no before_state")
            after = dict(next_before)
        else:
            after = dict(state)
        if schema == LEGACY_RECEIPT_SCHEMA:
            plan_hash = receipt.get("plan_sha256")
            plan = plans_by_hash.get(str(plan_hash))
            if plan is None:
                raise ValueError(
                    f"legacy transition[{index}] has no exact promotion plan candidate"
                )
            normalized.append(normalize_legacy_apply_receipt(receipt, plan, after))
            used_plan_hashes.add(str(plan_hash))
        elif schema == RECEIPT_SCHEMA:
            normalized.append(receipt)
        else:
            raise ValueError(f"transition[{index}] has unsupported receipt schema")
    unused = sorted(set(plans_by_hash) - used_plan_hashes)
    if unused:
        raise ValueError("unused legacy promotion plan candidates: " + ", ".join(unused))
    return normalized


def validate_transition_chain(
    chain: Mapping[str, Any], state: Mapping[str, Any]
) -> list[str]:
    """Replay the sealed MAIN chain from the canonical root to ``state``.

    Every apply embeds the exact plan that authorizes its state delta.  Every
    rollback embeds and identifies an earlier apply.  The release hashes this
    whole object, so runtime validation has no dependency on the mutable JSONL
    authoring ledger or on an asserted intermediate state.
    """

    errors = list(validate_state(state))
    expected_fields = {
        "schema_version", "pipeline_id", "root_state_sha256",
        "transition_count", "transitions", "final_state_sha256",
    }
    if set(chain) != expected_fields:
        errors.append("MAIN transition chain fields are not exact")
    if chain.get("schema_version") != TRANSITION_CHAIN_SCHEMA:
        errors.append(
            f"MAIN transition chain schema must be {TRANSITION_CHAIN_SCHEMA}"
        )
    if chain.get("pipeline_id") != PIPELINE_ID:
        errors.append("MAIN transition chain targets another pipeline")
    rows = chain.get("transitions")
    if not isinstance(rows, list):
        errors.append("MAIN transition chain transitions must be a list")
        rows = []
    if rows and isinstance(rows[0], Mapping):
        raw_root = rows[0].get("before_state")
    else:
        raw_root = state
    if raw_root == historical_default_state():
        root = historical_default_state()
    elif raw_root == default_state():
        root = default_state()
    else:
        root = default_state()
        errors.append("MAIN transition chain does not start at a canonical default")
    if chain.get("root_state_sha256") != fingerprint(root):
        errors.append("MAIN transition chain root hash mismatch")
    count = chain.get("transition_count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count != len(rows)
    ):
        errors.append("MAIN transition chain count mismatch")
    generation = state.get("generation")
    if generation != len(rows):
        errors.append("MAIN transition count must equal served generation")
    if chain.get("final_state_sha256") != fingerprint(state):
        errors.append("MAIN transition chain final state hash mismatch")

    running: dict[str, Any] = root
    receipt_ids: set[str] = set()
    applies: dict[str, dict[str, Any]] = {}
    for index, raw_receipt in enumerate(rows):
        label = f"transition[{index}]"
        if not isinstance(raw_receipt, dict):
            errors.append(f"{label} must be an object")
            continue
        receipt = raw_receipt
        if receipt.get("before_state") != running:
            errors.append(f"{label} before_state breaks the canonical chain")
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id or receipt_id in receipt_ids:
            errors.append(f"{label} receipt_id is invalid or duplicated")
        else:
            receipt_ids.add(receipt_id)

        if index + 1 < len(rows) and isinstance(rows[index + 1], dict):
            candidate_after = rows[index + 1].get("before_state")
        else:
            candidate_after = state
        if not isinstance(candidate_after, Mapping):
            errors.append(f"{label} has no provable after_state")
            candidate_after = {}
        after = dict(candidate_after)
        action = receipt.get("action")
        if action == "apply":
            promotion_id = receipt.get("promotion_id")
            if not isinstance(promotion_id, str) or promotion_id in applies:
                errors.append(f"{label} promotion apply is invalid or duplicated")
            else:
                applies[promotion_id] = receipt
            errors.extend(
                f"{label}: {item}" for item in validate_apply_receipt(receipt, after)
            )
            plan = receipt.get("promotion_plan")
            if isinstance(plan, dict):
                errors.extend(
                    f"{label}: {item}"
                    for item in validate_runtime_promotion_plan(plan, receipt, after)
                )
        elif action == "rollback":
            errors.extend(
                f"{label}: {item}"
                for item in validate_rollback_receipt(receipt, after)
            )
            promotion_id = receipt.get("promotion_id")
            if receipt.get("rolled_back_apply_receipt") != applies.get(promotion_id):
                errors.append(f"{label} does not reverse an exact prior chain apply")
        else:
            errors.append(f"{label} action must be apply or rollback")
        running = after
    if running != dict(state):
        errors.append("MAIN transition chain does not terminate at served state")
    return errors


def build_transition_chain(
    receipts: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    *,
    legacy_promotion_plans: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the strict self-contained artifact consumed by sealed serving.

    Legacy receipt normalization occurs only here, before artifact creation;
    :func:`validate_transition_chain` remains a v2-only runtime boundary.
    """

    rows = normalize_transition_receipts(
        receipts, state, legacy_promotion_plans=legacy_promotion_plans
    )
    if (
        rows and rows[0].get("before_state") == historical_default_state()
    ) or (not rows and dict(state) == historical_default_state()):
        root = historical_default_state()
    else:
        root = default_state()
    chain = {
        "schema_version": TRANSITION_CHAIN_SCHEMA,
        "pipeline_id": PIPELINE_ID,
        "root_state_sha256": fingerprint(root),
        "transition_count": len(rows),
        "transitions": rows,
        "final_state_sha256": fingerprint(state),
    }
    errors = validate_transition_chain(chain, state)
    if errors:
        raise ValueError("invalid MAIN transition chain: " + "; ".join(errors))
    return chain


def validate_runtime_promotion_plan(
    plan: dict[str, Any], receipt: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    """Purely prove that sealed plan bytes produced the served MAIN state.

    Authoring paths are deliberately not opened at runtime.  Their bytes were
    eligibility-checked by the promotion command; the release separately
    freezes this exact plan, its transition receipt, and the resulting state.
    """

    errors: list[str] = []
    expected_top = {
        "schema_version", "promotion_id", "created_at", "created_by",
        "source", "target", "changes", "validation_receipts", "rollback",
        "status",
    }
    if set(plan) != expected_top:
        errors.append("promotion plan fields are not exact")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        errors.append("promotion plan schema/status is invalid")
    apply_receipt = (
        receipt
        if receipt.get("action") == "apply"
        else receipt.get("rolled_back_apply_receipt")
    )
    if not isinstance(apply_receipt, dict):
        errors.append("promotion evidence has no apply receipt")
        return errors
    if fingerprint(plan) != apply_receipt.get("plan_sha256"):
        errors.append("promotion plan SHA-256 differs from the apply receipt")
    if plan.get("promotion_id") != apply_receipt.get("promotion_id"):
        errors.append("promotion plan ID differs from the apply receipt")
    if plan.get("source") != apply_receipt.get("source"):
        errors.append("promotion plan source differs from the apply receipt")

    before = apply_receipt.get("before_state")
    if not isinstance(before, dict):
        errors.append("apply receipt has no prior MAIN state")
        return errors
    target = plan.get("target")
    if not isinstance(target, dict) or set(target) != {
        "pipeline_id", "expected_generation", "expected_state_sha256"
    }:
        errors.append("promotion plan target fields are invalid")
        target = {}
    if target.get("pipeline_id") != PIPELINE_ID:
        errors.append("promotion plan targets another pipeline")
    if target.get("expected_generation") != before.get("generation"):
        errors.append("promotion plan expected generation is invalid")
    if target.get("expected_state_sha256") != fingerprint(before):
        errors.append("promotion plan expected state hash is invalid")
    rollback = plan.get("rollback")
    if not isinstance(rollback, dict) or set(rollback) != {
        "before_state", "before_state_sha256"
    }:
        errors.append("promotion plan rollback fields are invalid")
        rollback = {}
    if (
        rollback.get("before_state") != before
        or rollback.get("before_state_sha256") != fingerprint(before)
    ):
        errors.append("promotion plan rollback snapshot is invalid")

    changes = plan.get("changes")
    modern_change_fields = {"switches", "runtime_profile", "code_artifacts"}
    historical_change_fields = {"switches", "code_artifacts"}
    change_fields = set(changes) if isinstance(changes, dict) else set()
    if not isinstance(changes, dict) or change_fields not in (
        modern_change_fields, historical_change_fields
    ):
        errors.append("promotion plan change fields are invalid")
        changes = {}
        change_fields = set()
    if change_fields == historical_change_fields and "runtime_profile" in before:
        errors.append(
            "legacy promotion plan shape requires a historical profile-less state"
        )
    if (
        change_fields == historical_change_fields
        and "legacy_receipt" not in apply_receipt
    ):
        errors.append(
            "legacy promotion plan shape requires self-contained v1 evidence"
        )
    switches = changes.get("switches")
    if not isinstance(switches, dict) or any(
        not isinstance(key, str) or not isinstance(value, bool)
        for key, value in (switches.items() if isinstance(switches, dict) else ())
    ):
        errors.append("promotion plan switches are invalid")
        switches = {}
    profile = changes.get("runtime_profile")
    if profile is not None and (not isinstance(profile, str) or not profile):
        errors.append("promotion plan runtime profile is invalid")
    code_artifacts = changes.get("code_artifacts")
    if not isinstance(code_artifacts, list):
        errors.append("promotion plan code artifacts are invalid")
        code_artifacts = []
    for row in code_artifacts:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "bytes", "guard_switch"}
            or not isinstance(row.get("path"), str)
            or not row["path"]
            or not isinstance(row.get("bytes"), int)
            or isinstance(row.get("bytes"), bool)
            or row["bytes"] < 0
            or not isinstance(row.get("sha256"), str)
            or len(row["sha256"]) != 64
            or row.get("guard_switch") not in switches
        ):
            errors.append("promotion plan has an invalid code artifact record")

    validations = plan.get("validation_receipts")
    if not isinstance(validations, list) or not validations:
        errors.append("promotion plan has no validation receipt records")
    else:
        for row in validations:
            if (
                not isinstance(row, dict)
                or set(row) != {"path", "sha256", "bytes"}
                or not isinstance(row.get("path"), str)
                or not row["path"]
                or not isinstance(row.get("bytes"), int)
                or isinstance(row.get("bytes"), bool)
                or row["bytes"] < 0
                or not isinstance(row.get("sha256"), str)
                or len(row["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in row["sha256"])
            ):
                errors.append("promotion plan has an invalid validation receipt record")

    expected = deepcopy(before)
    raw_generation = before.get("generation")
    if isinstance(raw_generation, bool) or not isinstance(raw_generation, int):
        errors.append("promotion plan prior generation is invalid")
        raw_generation = -1
    expected["generation"] = raw_generation + 1
    expected["active_promotion_id"] = apply_receipt.get("promotion_id")
    source = apply_receipt.get("source") if isinstance(
        apply_receipt.get("source"), dict
    ) else {}
    expected.setdefault("active_promotions", []).append(
        {
            "promotion_id": apply_receipt.get("promotion_id"),
            "adr_id": source.get("adr_id"),
            "experiment_id": source.get("experiment_id"),
            "arm_id": source.get("arm_id"),
            "source_manifest_sha256": source.get("manifest_sha256"),
            "applied_at": apply_receipt.get("at"),
            "applied_by": apply_receipt.get("actor"),
        }
    )
    expected.setdefault("switches", {}).update(switches)
    if profile is not None:
        expected["runtime_profile"] = profile
    by_path = {
        str(row.get("path")): row
        for row in expected.setdefault("code_artifacts", [])
        if isinstance(row, dict)
    }
    by_path.update(
        {
            str(row.get("path")): row
            for row in code_artifacts
            if isinstance(row, dict)
        }
    )
    expected["code_artifacts"] = list(by_path.values())
    expected["updated_at"] = apply_receipt.get("at")

    historical_state = state
    if receipt.get("action") == "rollback":
        historical_state = deepcopy(receipt.get("before_state") or {})
        historical_state["generation"] = expected["generation"]
        historical_state["updated_at"] = expected["updated_at"]
    if expected != historical_state:
        errors.append("promotion plan changes do not produce the proved MAIN state")
    return errors


def runtime_provenance() -> dict[str, Any]:
    try:
        state = load_state()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "pipeline_id": PIPELINE_ID,
            "generation": 0,
            "status": "invalid_manifest_fallback",
            "error": str(exc),
            "active_promotion_id": None,
            "sources": [],
        }
    return {
        "pipeline_id": state["pipeline_id"],
        "runtime_profile": state.get("runtime_profile", PIPELINE_ID),
        "generation": state["generation"],
        "status": "promoted" if state["active_promotions"] else "repository_default",
        "active_promotion_id": state.get("active_promotion_id"),
        "sources": [
            {
                "promotion_id": row.get("promotion_id"),
                "adr_id": row.get("adr_id"),
                "experiment_id": row.get("experiment_id"),
                "arm_id": row.get("arm_id"),
            }
            for row in state.get("active_promotions", [])
        ],
    }


def switch_overrides() -> dict[str, bool]:
    try:
        state = load_state()
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return {
        str(key): bool(value) for key, value in state.get("switches", {}).items()
        if isinstance(value, bool)
    }


def runtime_profile_id() -> str:
    """Return the production registry ID selected by the current generation."""
    try:
        state = load_state()
    except (OSError, ValueError, json.JSONDecodeError):
        return PIPELINE_ID
    return str(state.get("runtime_profile") or PIPELINE_ID)


def _front_matter(path: Path) -> dict[str, str]:
    lines = path.read_text("utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _source_readme(manifest: Path) -> Path:
    if manifest.parent.name != "실험":
        raise ValueError("source manifest must be ADR/실험/manifest.json")
    return manifest.parent.parent / "README.md"


def _allowed_switches() -> set[str]:
    from lawrag.core.rag import switches
    return {str(row["key"]) for row in switches.REGISTRY}


def _source_errors(manifest_path: Path, arm_id: str) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if not manifest_path.is_file():
        return [f"source manifest missing: {manifest_path}"], {}
    manifest = json.loads(manifest_path.read_text("utf-8"))
    readme_path = _source_readme(manifest_path)
    meta = _front_matter(readme_path) if readme_path.is_file() else {}
    if meta.get("status") != "Accepted":
        errors.append("source ADR status must be Accepted")
    if meta.get("main_wiring") not in {"promotion-candidate", "changed"}:
        errors.append("source ADR main_wiring must be promotion-candidate or changed")
    if manifest.get("decision_eligible") is not True:
        errors.append("source experiment must set decision_eligible=true")
    if manifest.get("in_sample") is True:
        errors.append("in-sample source cannot be promoted to MAIN")
    if manifest.get("results", {}).get("status") != "complete":
        errors.append("source experiment results must be complete")
    arms = {
        str(row.get("id")): row for row in manifest.get("design", {}).get("arms", [])
        if isinstance(row, dict)
    }
    if arm_id not in arms:
        errors.append(f"source arm does not exist: {arm_id}")
    reservation = manifest.get("reservation")
    if isinstance(reservation, dict) and reservation.get("status") != "completed":
        errors.append("source ADR reservation must be completed")
    raw = manifest_path.read_text("utf-8")
    if "TODO" in raw or "PENDING" in raw:
        errors.append("source manifest contains unresolved TODO or PENDING")
    return errors, manifest


def _artifact_record(path: Path, guard_switch: str | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    row: dict[str, Any] = {
        "path": str(resolved),
        "sha256": file_sha256(resolved),
        "bytes": resolved.stat().st_size,
    }
    if guard_switch is not None:
        row["guard_switch"] = guard_switch
    return row


def prepare_plan(
    source_manifest: Path,
    arm_id: str,
    *,
    switch_changes: dict[str, bool],
    runtime_profile: str | None = None,
    code_artifacts: Iterable[tuple[Path, str]] = (),
    validation_receipts: Iterable[Path] = (),
    actor: str,
) -> dict[str, Any]:
    source_manifest = source_manifest.resolve()
    source_errors, source = _source_errors(source_manifest, arm_id)
    if source_errors:
        raise ValueError("; ".join(source_errors))
    allowed = _allowed_switches()
    unknown = sorted(set(switch_changes) - allowed)
    if unknown:
        raise ValueError("unknown MAIN switches: " + ", ".join(unknown))
    if switch_changes.get("legalclosure_main") is False:
        raise ValueError("promotion cannot disable legalclosure_main")
    if runtime_profile is not None:
        from lawrag.runtime.registry import validate_profile_id
        validate_profile_id(runtime_profile)
    if not switch_changes and runtime_profile is None:
        raise ValueError(
            "promotion requires a guarded switch change or runtime_profile change"
        )
    artifacts = [_artifact_record(path, guard) for path, guard in code_artifacts]
    for row in artifacts:
        guard = str(row.get("guard_switch", ""))
        if guard not in allowed:
            raise ValueError(f"code artifact has unknown guard switch: {guard}")
        if guard not in switch_changes:
            raise ValueError(f"code artifact guard switch is not in promotion changes: {guard}")
    receipts = [_artifact_record(path) for path in validation_receipts]
    if not receipts:
        raise ValueError("promotion requires at least one validation receipt")
    state = load_state()
    created_at = _now()
    promotion_id = f"main-{created_at[:10].replace('-', '')}-{uuid.uuid4().hex[:12]}"
    return {
        "schema_version": PLAN_SCHEMA,
        "promotion_id": promotion_id,
        "created_at": created_at,
        "created_by": actor,
        "source": {
            "adr_id": source.get("adr_id"),
            "experiment_id": source.get("experiment_id"),
            "arm_id": arm_id,
            "manifest_path": str(source_manifest),
            "manifest_sha256": file_sha256(source_manifest),
        },
        "target": {
            "pipeline_id": PIPELINE_ID,
            "expected_generation": state["generation"],
            "expected_state_sha256": fingerprint(state),
        },
        "changes": {
            "switches": {str(key): bool(value) for key, value in switch_changes.items()},
            "runtime_profile": runtime_profile,
            "code_artifacts": artifacts,
        },
        "validation_receipts": receipts,
        "rollback": {
            "before_state": state,
            "before_state_sha256": fingerprint(state),
        },
        "status": "ready",
    }


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("schema_version") != PLAN_SCHEMA:
        errors.append(f"plan schema_version must be {PLAN_SCHEMA}")
    if plan.get("status") != "ready":
        errors.append("plan status must be ready")
    source = plan.get("source", {})
    source_path = Path(str(source.get("manifest_path", "")))
    if not source_path.is_file():
        errors.append(f"source manifest missing: {source_path}")
    else:
        if source.get("manifest_sha256") != file_sha256(source_path):
            errors.append("source manifest hash mismatch")
        else:
            source_errors, manifest = _source_errors(source_path, str(source.get("arm_id", "")))
            errors.extend(source_errors)
            if source.get("adr_id") != manifest.get("adr_id"):
                errors.append("source ADR ID mismatch")
            if source.get("experiment_id") != manifest.get("experiment_id"):
                errors.append("source experiment ID mismatch")
    target = plan.get("target", {})
    try:
        state = load_state()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        state = default_state()
    if target.get("pipeline_id") != PIPELINE_ID:
        errors.append(f"target pipeline must be {PIPELINE_ID}")
    if target.get("expected_generation") != state["generation"]:
        errors.append("stale plan: MAIN generation changed")
    if target.get("expected_state_sha256") != fingerprint(state):
        errors.append("stale plan: MAIN state hash changed")
    if any(
            row.get("experiment_id") == source.get("experiment_id") and
            row.get("arm_id") == source.get("arm_id")
            for row in state.get("active_promotions", [])):
        errors.append("source experiment arm is already active in MAIN")
    changes = plan.get("changes", {})
    raw_switches = changes.get("switches")
    runtime_profile = changes.get("runtime_profile")
    if not isinstance(raw_switches, dict):
        errors.append("plan switches must be an object")
        raw_switches = {}
    if not raw_switches and runtime_profile is None:
        errors.append("plan requires switch changes or runtime_profile")
    if runtime_profile is not None:
        try:
            from lawrag.runtime.registry import validate_profile_id
            validate_profile_id(str(runtime_profile))
        except ValueError as exc:
            errors.append(str(exc))
    allowed = _allowed_switches()
    for key, value in raw_switches.items():
        if key not in allowed:
            errors.append(f"unknown MAIN switch: {key}")
        if not isinstance(value, bool):
            errors.append(f"MAIN switch must be boolean: {key}")
    if raw_switches.get("legalclosure_main") is False:
        errors.append("promotion cannot disable legalclosure_main")
    for row in changes.get("code_artifacts", []):
        path = Path(str(row.get("path", "")))
        if not path.is_file() or row.get("sha256") != file_sha256(path):
            errors.append(f"code artifact missing or changed: {path}")
        guard = row.get("guard_switch")
        if guard not in raw_switches:
            errors.append(f"code artifact guard is not promoted: {guard}")
    receipts = plan.get("validation_receipts")
    if not isinstance(receipts, list) or not receipts:
        errors.append("plan requires validation receipts")
    else:
        for row in receipts:
            path = Path(str(row.get("path", "")))
            if not path.is_file() or row.get("sha256") != file_sha256(path):
                errors.append(f"validation receipt missing or changed: {path}")
    rollback = plan.get("rollback", {})
    if rollback.get("before_state_sha256") != fingerprint(rollback.get("before_state")):
        errors.append("rollback snapshot hash mismatch")
    if rollback.get("before_state_sha256") != target.get("expected_state_sha256"):
        errors.append("rollback snapshot does not match expected MAIN state")
    if any(marker in json.dumps(plan, ensure_ascii=False) for marker in ("TODO", "PENDING")):
        errors.append("promotion plan contains unresolved TODO or PENDING")
    return errors


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _append_receipt(
    receipt: dict[str, Any],
    *,
    legacy_promotion_plans: Iterable[Mapping[str, Any]] = (),
) -> None:
    existing = read_receipts(
        legacy_promotion_plans=legacy_promotion_plans,
        state=receipt.get("before_state"),
    )
    if existing and receipt.get("before_state_sha256") != existing[-1].get(
        "after_state_sha256"
    ):
        raise ValueError("MAIN receipt ledger transition is not contiguous")
    if any(row.get("receipt_id") == receipt.get("receipt_id") for row in existing):
        raise ValueError("MAIN receipt_id is not unique")
    if receipt.get("action") == "apply" and any(
        row.get("action") == "apply"
        and row.get("promotion_id") == receipt.get("promotion_id")
        for row in existing
    ):
        raise ValueError("MAIN promotion_id already has an apply receipt")
    # The manifest is atomically written before this append.  Prove the whole
    # candidate ledger against that exact state before persisting its new tip.
    build_transition_chain([*existing, receipt], load_state())
    path = receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _promotion_lock(actor: str):
    path = manifest_path().with_name(".promotion.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"actor": actor, "pid": os.getpid(), "created_at": _now()}
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False)
            stream.write("\n")
    except FileExistsError as exc:
        holder = path.read_text("utf-8").strip() if path.is_file() else "<unknown>"
        raise ValueError(f"another MAIN promotion holds {path}: {holder}") from exc
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def apply_plan(
    plan: dict[str, Any],
    *,
    actor: str,
    approval_note: str,
    confirm_main: bool,
    legacy_promotion_plans: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    legacy_promotion_plans = tuple(legacy_promotion_plans)
    if not confirm_main:
        raise ValueError("MAIN promotion requires explicit confirm_main=true")
    if not approval_note.strip():
        raise ValueError("MAIN promotion requires a non-empty approval note")
    with _promotion_lock(actor):
        errors = validate_plan(plan)
        if errors:
            raise ValueError("invalid promotion plan: " + "; ".join(errors))
        before = load_state()
        source = plan["source"]
        promotion = {
            "promotion_id": plan["promotion_id"],
            "adr_id": source["adr_id"],
            "experiment_id": source["experiment_id"],
            "arm_id": source["arm_id"],
            "source_manifest_sha256": source["manifest_sha256"],
            "applied_at": _now(),
            "applied_by": actor,
        }
        after = deepcopy(before)
        after["generation"] = before["generation"] + 1
        after["active_promotion_id"] = plan["promotion_id"]
        after.setdefault("active_promotions", []).append(promotion)
        after.setdefault("switches", {}).update(plan["changes"]["switches"])
        selected_profile = plan["changes"].get("runtime_profile")
        if selected_profile is not None:
            after["runtime_profile"] = selected_profile
        artifact_by_path = {
            str(row.get("path")): row for row in after.setdefault("code_artifacts", [])}
        artifact_by_path.update({
            str(row.get("path")): row for row in plan["changes"].get("code_artifacts", [])})
        after["code_artifacts"] = list(artifact_by_path.values())
        after["updated_at"] = promotion["applied_at"]
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "receipt_id": f"mpr-{uuid.uuid4().hex[:16]}",
            "action": "apply",
            "promotion_id": plan["promotion_id"],
            "at": promotion["applied_at"],
            "actor": actor,
            "approval_note": approval_note,
            "plan_sha256": fingerprint(plan),
            "promotion_plan": deepcopy(plan),
            "source": source,
            "before_state": before,
            "before_state_sha256": fingerprint(before),
            "after_state_sha256": fingerprint(after),
        }
        receipt_errors = validate_apply_receipt(receipt, after)
        receipt_errors.extend(validate_runtime_promotion_plan(plan, receipt, after))
        if receipt_errors:
            raise ValueError(
                "generated MAIN apply receipt is invalid: "
                + "; ".join(receipt_errors)
            )
        _atomic_write(manifest_path(), after)
        try:
            _append_receipt(
                receipt, legacy_promotion_plans=legacy_promotion_plans
            )
        except Exception:
            _atomic_write(manifest_path(), before)
            raise
        return {
            "state": after,
            "receipt": receipt,
            "transition_chain": build_transition_chain(
                read_receipts(legacy_promotion_plans=legacy_promotion_plans), after
            ),
        }


def read_receipts(
    *,
    legacy_promotion_plans: Iterable[Mapping[str, Any]] = (),
    state: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    path = receipts_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    receipt_ids: set[str] = set()
    apply_ids: set[str] = set()
    previous_after: str | None = None
    for line_number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"MAIN receipt line {line_number} is not an object")
            if value.get("schema_version") not in {
                RECEIPT_SCHEMA, LEGACY_RECEIPT_SCHEMA
            }:
                raise ValueError(f"MAIN receipt line {line_number} has wrong schema")
            if (
                value.get("schema_version") == LEGACY_RECEIPT_SCHEMA
                and value.get("action") != "apply"
            ):
                raise ValueError(
                    f"MAIN receipt line {line_number} has unsupported legacy action"
                )
            if value.get("action") not in {"apply", "rollback"}:
                raise ValueError(f"MAIN receipt line {line_number} has wrong action")
            receipt_id = value.get("receipt_id")
            promotion_id = value.get("promotion_id")
            if (
                not isinstance(receipt_id, str)
                or not receipt_id
                or receipt_id in receipt_ids
                or not isinstance(promotion_id, str)
                or not promotion_id
            ):
                raise ValueError(f"MAIN receipt line {line_number} has duplicate/invalid ID")
            if previous_after is not None and value.get(
                "before_state_sha256"
            ) != previous_after:
                raise ValueError("MAIN receipt ledger transition chain is broken")
            if value.get("action") == "apply":
                if promotion_id in apply_ids:
                    raise ValueError("MAIN receipt ledger has duplicate promotion apply")
                apply_ids.add(promotion_id)
            else:
                embedded = value.get("rolled_back_apply_receipt")
                if (
                    not isinstance(embedded, dict)
                    or embedded.get("promotion_id") != promotion_id
                    or fingerprint(embedded)
                    != value.get("rolled_back_apply_receipt_sha256")
                ):
                    raise ValueError("MAIN rollback receipt has an invalid apply reference")
            receipt_ids.add(receipt_id)
            previous_after = value.get("after_state_sha256")
            rows.append(value)
    state = deepcopy(dict(state)) if state is not None else load_state()
    normalized = normalize_transition_receipts(
        rows, state, legacy_promotion_plans=legacy_promotion_plans
    )
    applies: dict[str, dict[str, Any]] = {}
    for row in normalized:
        promotion_id = str(row.get("promotion_id") or "")
        if row.get("action") == "apply":
            applies[promotion_id] = row
        elif row.get("rolled_back_apply_receipt") != applies.get(promotion_id):
            raise ValueError("MAIN rollback does not embed the normalized ledger apply")
    # This proves the in-memory bridge while leaving the source ledger bytes
    # untouched.  Runtime receives only the resulting sealed chain artifact.
    build_transition_chain(normalized, state)
    return normalized


def rollback(
    promotion_id: str,
    *,
    actor: str,
    note: str,
    confirm_main: bool,
    legacy_promotion_plans: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    legacy_promotion_plans = tuple(legacy_promotion_plans)
    if not confirm_main:
        raise ValueError("MAIN rollback requires explicit confirm_main=true")
    if not note.strip():
        raise ValueError("MAIN rollback requires a non-empty note")
    with _promotion_lock(actor):
        current = load_state()
        if current.get("active_promotion_id") != promotion_id:
            raise ValueError("only the latest active promotion can be rolled back")
        apply_receipts = [
            row for row in read_receipts(
                legacy_promotion_plans=legacy_promotion_plans
            )
            if row.get("action") == "apply"
            and row.get("promotion_id") == promotion_id
        ]
        if len(apply_receipts) != 1:
            raise ValueError(f"apply receipt not found: {promotion_id}")
        apply_receipt = apply_receipts[0]
        restored = deepcopy(apply_receipt["before_state"])
        restored["generation"] = current["generation"] + 1
        restored["updated_at"] = _now()
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "receipt_id": f"mpr-{uuid.uuid4().hex[:16]}",
            "action": "rollback",
            "promotion_id": promotion_id,
            "at": restored["updated_at"],
            "actor": actor,
            "note": note,
            "before_state": current,
            "before_state_sha256": fingerprint(current),
            "after_state_sha256": fingerprint(restored),
            "rolled_back_apply_receipt": deepcopy(apply_receipt),
            "rolled_back_apply_receipt_sha256": fingerprint(apply_receipt),
        }
        receipt_errors = validate_rollback_receipt(receipt, restored)
        if receipt_errors:
            raise ValueError(
                "generated MAIN rollback receipt is invalid: "
                + "; ".join(receipt_errors)
            )
        _atomic_write(manifest_path(), restored)
        try:
            _append_receipt(
                receipt, legacy_promotion_plans=legacy_promotion_plans
            )
        except Exception:
            _atomic_write(manifest_path(), current)
            raise
        return {
            "state": restored,
            "receipt": receipt,
            "transition_chain": build_transition_chain(
                read_receipts(legacy_promotion_plans=legacy_promotion_plans),
                restored,
            ),
        }
