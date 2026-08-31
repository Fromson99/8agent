"""ADR arm을 운영 MAIN RAG 배선에 원자적으로 승격하는 원장.

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
from typing import Any, Iterable

from lawrag.core.rag.index import store_path


PIPELINE_SCHEMA = "main-rag-pipeline-v1"
PLAN_SCHEMA = "main-rag-promotion-plan-v1"
RECEIPT_SCHEMA = "main-rag-promotion-receipt-v1"
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
        "generation": 0,
        "active_promotion_id": None,
        "active_promotions": [],
        "switches": {},
        "code_artifacts": [],
        "updated_at": None,
    }


def _validate_state(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if state.get("schema_version") != PIPELINE_SCHEMA:
        errors.append(f"schema_version must be {PIPELINE_SCHEMA}")
    if state.get("pipeline_id") != PIPELINE_ID:
        errors.append(f"pipeline_id must be {PIPELINE_ID}")
    if not isinstance(state.get("generation"), int) or state.get("generation", -1) < 0:
        errors.append("generation must be a non-negative integer")
    if not isinstance(state.get("active_promotions"), list):
        errors.append("active_promotions must be a list")
    if not isinstance(state.get("switches"), dict):
        errors.append("switches must be an object")
    if not isinstance(state.get("code_artifacts"), list):
        errors.append("code_artifacts must be a list")
    return errors


def load_state() -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        return default_state()
    state = json.loads(path.read_text("utf-8"))
    errors = _validate_state(state)
    if errors:
        raise ValueError("invalid MAIN pipeline manifest: " + "; ".join(errors))
    return state


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
    if not switch_changes:
        raise ValueError("promotion requires at least one guarded switch change")
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
    if not isinstance(raw_switches, dict) or not raw_switches:
        errors.append("plan requires switch changes")
        raw_switches = {}
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


def _append_receipt(receipt: dict[str, Any]) -> None:
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
) -> dict[str, Any]:
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
        artifact_by_path = {
            str(row.get("path")): row for row in after.setdefault("code_artifacts", [])}
        artifact_by_path.update({
            str(row.get("path")): row for row in plan["changes"].get("code_artifacts", [])})
        after["code_artifacts"] = list(artifact_by_path.values())
        after["updated_at"] = promotion["applied_at"]
        _atomic_write(manifest_path(), after)
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "receipt_id": f"mpr-{uuid.uuid4().hex[:16]}",
            "action": "apply",
            "promotion_id": plan["promotion_id"],
            "at": promotion["applied_at"],
            "actor": actor,
            "approval_note": approval_note,
            "plan_sha256": fingerprint(plan),
            "source": source,
            "before_state": before,
            "before_state_sha256": fingerprint(before),
            "after_state_sha256": fingerprint(after),
        }
        try:
            _append_receipt(receipt)
        except Exception:
            _atomic_write(manifest_path(), before)
            raise
        return {"state": after, "receipt": receipt}


def read_receipts() -> list[dict[str, Any]]:
    path = receipts_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def rollback(
    promotion_id: str,
    *,
    actor: str,
    note: str,
    confirm_main: bool,
) -> dict[str, Any]:
    if not confirm_main:
        raise ValueError("MAIN rollback requires explicit confirm_main=true")
    if not note.strip():
        raise ValueError("MAIN rollback requires a non-empty note")
    with _promotion_lock(actor):
        current = load_state()
        if current.get("active_promotion_id") != promotion_id:
            raise ValueError("only the latest active promotion can be rolled back")
        apply_receipt = next((
            row for row in reversed(read_receipts())
            if row.get("action") == "apply" and row.get("promotion_id") == promotion_id), None)
        if apply_receipt is None:
            raise ValueError(f"apply receipt not found: {promotion_id}")
        restored = deepcopy(apply_receipt["before_state"])
        restored["generation"] = current["generation"] + 1
        restored["updated_at"] = _now()
        _atomic_write(manifest_path(), restored)
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "receipt_id": f"mpr-{uuid.uuid4().hex[:16]}",
            "action": "rollback",
            "promotion_id": promotion_id,
            "at": restored["updated_at"],
            "actor": actor,
            "note": note,
            "before_state_sha256": fingerprint(current),
            "after_state_sha256": fingerprint(restored),
            "rolled_back_apply_receipt": apply_receipt["receipt_id"],
        }
        try:
            _append_receipt(receipt)
        except Exception:
            _atomic_write(manifest_path(), current)
            raise
        return {"state": restored, "receipt": receipt}
