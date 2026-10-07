"""Read-only lifecycle status and contract validation shared by CLI and API."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from lawrag.platform.paths import data_path, repository_root

from .catalog import load_catalog, stages_by_phase, validate_catalog


PIPELINE_SCHEMA = Path("00_SYSTEM/SCHEMAS/legal-ontology-lifecycle-v1.schema.json")
DEFINITION_SCHEMA = Path("00_SYSTEM/SCHEMAS/definition-projection-v1.schema.json")
DEFINITION_EXAMPLE = Path("01_DATA/CONTRACTS/definition-projection-v1.example.json")
FEEDBACK_SCHEMA = Path("00_SYSTEM/SCHEMAS/feedback-event-v1.schema.json")
FEEDBACK_EXAMPLE = Path("01_DATA/CONTRACTS/feedback-event-v1.example.json")
CHANGE_CANDIDATE_SCHEMA = Path("00_SYSTEM/SCHEMAS/change-candidate-v1.schema.json")
CHANGE_CANDIDATE_EXAMPLE = Path("01_DATA/CONTRACTS/change-candidate-v1.example.json")


def _pipeline_path() -> Path:
    return Path(
        os.environ.get("ONTOLOGY_PIPELINE_FILE")
        or repository_root() / "00_SYSTEM/ONTOLOGY_PIPELINE.json"
    )


def _definition_schema_path() -> Path:
    return Path(
        os.environ.get("DEFINITION_PROJECTION_SCHEMA")
        or repository_root() / DEFINITION_SCHEMA
    )


def definition_projection_dir() -> Path:
    return Path(
        os.environ.get("DEFINITION_PROJECTION_DIR")
        or data_path("PROJECTIONS", "DEFINITIONS")
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _definition_main_binding() -> dict[str, Any]:
    """Read the canonical MAIN manifest instead of reporting a static label."""

    from lawrag.platform import main_promotion

    try:
        state = main_promotion.load_state()
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {
            "runtime_wired": False,
            "runtime_profile": None,
            "main_generation": None,
            "main_promotion_id": None,
            "main_status": f"MAIN 확인 실패: {type(exc).__name__}: {exc}",
        }
    profile = str(state.get("runtime_profile") or main_promotion.PIPELINE_ID)
    switches = state.get("switches") or {}
    wired = (
        profile == "ontology-rag-v1"
        and isinstance(switches, Mapping)
        and switches.get("legalclosure_main") is True
    )
    generation = state.get("generation")
    status = (
        f"MAIN 배선됨 ({profile} · gen {generation})"
        if wired
        else f"MAIN 미배선 (현재 {profile} · gen {generation})"
    )
    return {
        "runtime_wired": wired,
        "runtime_profile": profile,
        "main_generation": generation,
        "main_promotion_id": state.get("active_promotion_id"),
        "main_status": status,
    }


def _jsonschema_validate(schema_path: Path, instance_path: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return ["jsonschema package is unavailable"]
    try:
        schema = _json(schema_path)
        instance = _json(instance_path)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        return [
            f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
            for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
        ]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"{type(exc).__name__}: {exc}"]


def definition_projection_status(root: Path | None = None) -> dict[str, Any]:
    base = root or definition_projection_dir()
    if (base / "CURRENT.json").is_file():
        try:
            from lawrag.ontology.definition_projection import DefinitionProjectionStore

            store = DefinitionProjectionStore(base)
            verified = store.verify()
            main_binding = _definition_main_binding()
            records = [{
                "name": row["projection_id"],
                "file": "records.jsonl",
                "status": row["status"],
                "valid": True,
                "errors": [],
            } for row in store.records()]
            return {
                "pending": 0,
                "total": verified["total"],
                "detail": [],
                "records": records,
                "valid": verified["valid"],
                "invalid": verified["invalid"],
                "ready": verified["ready"],
                "ambiguous_surfaces_withheld": verified["ambiguous_surfaces_withheld"],
                "excluded_terms_withheld": verified["excluded_terms_withheld"],
                "multi_owner_ready_surfaces": verified["multi_owner_ready_surfaces"],
                "generation_id": verified["generation_id"],
                "source_graph_generation": verified["source_graph_generation"],
                **main_binding,
                "note": (
                    f"{verified['generation_id']} · Projection {verified['total']} · "
                    f"READY {verified['ready']} · 충돌 surface "
                    f"{verified['ambiguous_surfaces_withheld']}개 격리 · "
                    f"hash/receipt 검증됨 · {main_binding['main_status']}"
                ),
            }
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return {
                "pending": 1,
                "total": 1,
                "detail": [{"name": "DefinitionProjection", "reason": str(exc)}],
                "records": [],
                "valid": 0,
                "invalid": 1,
                "ready": 0,
                "generation_id": None,
                "note": f"DefinitionProjection 준비 필요: {exc}",
            }
    files = sorted(path for path in base.glob("*.json") if path.is_file() and not path.is_symlink()) if base.is_dir() else []
    schema = _definition_schema_path()
    details: list[dict[str, Any]] = []
    valid = 0
    for path in files:
        errors = _jsonschema_validate(schema, path)
        try:
            value = _json(path)
            status = str(value.get("status") or "") if isinstance(value, Mapping) else ""
            projection_id = str(value.get("projection_id") or path.stem) if isinstance(value, Mapping) else path.stem
        except (OSError, UnicodeError, json.JSONDecodeError):
            status, projection_id = "", path.stem
        if not errors:
            valid += 1
        details.append({
            "name": projection_id,
            "file": path.name,
            "status": status,
            "valid": not errors,
            "errors": errors[:5],
        })
    invalid = len(files) - valid
    note = (
        f"Projection {len(files)} · valid {valid} · invalid {invalid}"
        if files
        else "Projection 0 · 선택 기능 — 적용 불가 시 Canonical 탐색"
    )
    return {
        "pending": invalid,
        "total": len(files),
        "detail": [row for row in details if not row["valid"]],
        "records": details,
        "valid": valid,
        "invalid": invalid,
        "note": note,
    }


def legal_graph_status(root: Path | None = None) -> dict[str, Any]:
    base = root or Path(os.environ.get("LEGAL_GRAPH_STORE") or data_path("legal_graph"))
    pointer_path = base / "CURRENT.json"
    detail: list[dict[str, Any]] = []
    try:
        pointer = _json(pointer_path)
        manifest_relative = str(pointer.get("manifest") or "")
        manifest_path = (base / manifest_relative).resolve()
        manifest_path.relative_to(base.resolve())
        manifest = _json(manifest_path)
        generation_id = str(pointer.get("generation_id") or "")
        if generation_id != str(manifest.get("generation_id") or ""):
            raise ValueError("CURRENT generation and manifest generation differ")
        content = dict(manifest)
        claimed_content = str(content.pop("content_sha256", ""))
        if claimed_content != _canonical_sha256(content):
            raise ValueError("manifest content_sha256 mismatch")
        if claimed_content != str(pointer.get("content_sha256") or ""):
            raise ValueError("CURRENT content_sha256 mismatch")
        validation_path = manifest_path.parent / "validation" / "summary.json"
        validation = _json(validation_path)
        if validation.get("ok") is not True or validation.get("generation_id") != generation_id:
            raise ValueError("independent validation receipt is missing or failed")
        artifacts = manifest.get("artifacts") or {}
        layer_rows = {
            layer: sum(
                int(meta.get("rows") or 0)
                for path, meta in artifacts.items()
                if isinstance(meta, Mapping) and str(path).startswith(prefix)
            )
            for layer, prefix in (
                ("canonical", "canonical/"),
                ("observation", "observations/"),
                ("projection", "projections/"),
            )
        }
        clause_spans = int((artifacts.get("canonical/clause_spans.jsonl.gz") or artifacts.get("canonical/clause_spans.jsonl") or {}).get("rows") or 0)
        from lawrag.core.legal_graph import COMPILER_CONTRACT_VERSION

        compiler = str(manifest.get("compiler_contract") or "")
        pending = int(compiler != COMPILER_CONTRACT_VERSION or clause_spans == 0)
        if pending:
            detail.append({
                "name": generation_id,
                "reason": f"현재 {compiler}, 목표 {COMPILER_CONTRACT_VERSION}, ClauseSpan {clause_spans:,}",
            })
        return {
            "pending": pending,
            "total": 1,
            "detail": detail,
            "generation_id": generation_id,
            "compiler_contract": compiler,
            "runtime_wired": bool(manifest.get("runtime_wired")),
            "validation": {
                "ok": True,
                "checked_rows": int(validation.get("checked_rows") or 0),
                "warning_count": int(validation.get("warning_count") or 0),
            },
            "layer_rows": layer_rows,
            "clause_spans": clause_spans,
            "note": (
                f"{generation_id} · Canonical {layer_rows['canonical']:,} · "
                f"Observation {layer_rows['observation']:,} · Projection {layer_rows['projection']:,} · "
                f"ClauseSpan {clause_spans:,}"
                + (" · 명시 재빌드 필요" if pending else " · 검증됨")
            ),
        }
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {
            "pending": 1,
            "total": 1,
            "detail": [{"name": "Legal Graph", "reason": str(exc)}],
            "generation_id": None,
            "runtime_wired": False,
            "validation": {"ok": False},
            "layer_rows": {"canonical": 0, "observation": 0, "projection": 0},
            "clause_spans": 0,
            "note": f"Legal Graph 준비 필요: {exc}",
        }


def feedback_status() -> dict[str, Any]:
    """Fold persisted ontology feedback without granting it serving authority."""

    try:
        from lawrag.core.rag import tuples as tuples_mod
        from lawrag.feedback.lifecycle import compile_change_candidates

        rows = tuples_mod.read(limit=10_000)
        events = []
        for row in rows:
            feedback = row.get("피드백") or {}
            event = feedback.get("ontology_feedback")
            if isinstance(event, Mapping):
                events.append(dict(event))
        candidates = list(compile_change_candidates(events))
        active = [row for row in candidates if row.get("status") == "CANDIDATE"]
        by_kind: dict[str, int] = {}
        for row in active:
            kind = str(row.get("candidate_kind") or "UNKNOWN")
            by_kind[kind] = by_kind.get(kind, 0) + 1
        counts = " · ".join(
            f"{kind} {count}" for kind, count in sorted(by_kind.items())
        )
        return {
            "pending": len(active),
            "total": len(candidates),
            "detail": [{
                "name": row["candidate_id"],
                "kind": row["candidate_kind"],
                "status": row["status"],
                "events": row["evidence"]["example_count"],
            } for row in candidates],
            "events": len(events),
            "resolved": len(candidates) - len(active),
            "note": (
                f"FeedbackEvent {len(events)} · ChangeCandidate {len(candidates)}"
                + (f" · {counts}" if counts else " · 검토 후보 없음")
                + " · 자동 승격 없음"
            ),
        }
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        return {
            "pending": 1,
            "total": 1,
            "detail": [{"name": "feedback", "reason": str(exc)}],
            "events": 0,
            "resolved": 0,
            "note": f"피드백 계보 확인 실패: {exc}",
        }


def contract_report(*, projection_root: Path | None = None) -> dict[str, Any]:
    root = repository_root()
    checks: list[dict[str, Any]] = []
    pipeline_target = _pipeline_path()
    pipeline_errors = _jsonschema_validate(root / PIPELINE_SCHEMA, pipeline_target)
    try:
        from lawrag.core import batch as batch_mod

        validate_catalog(load_catalog(pipeline_target), runner_stages=batch_mod.STAGES)
    except (ValueError, OSError) as exc:
        pipeline_errors.append(str(exc))
    checks.append({
        "id": "lifecycle",
        "schema": str(PIPELINE_SCHEMA),
        "target": str(pipeline_target),
        "ok": not pipeline_errors,
        "errors": pipeline_errors,
    })

    definition_errors = _jsonschema_validate(_definition_schema_path(), root / DEFINITION_EXAMPLE)
    checks.append({
        "id": "definition-example",
        "schema": str(DEFINITION_SCHEMA),
        "target": str(DEFINITION_EXAMPLE),
        "ok": not definition_errors,
        "errors": definition_errors,
    })
    for check_id, schema_path, example_path in (
        ("feedback-example", FEEDBACK_SCHEMA, FEEDBACK_EXAMPLE),
        ("change-candidate-example", CHANGE_CANDIDATE_SCHEMA, CHANGE_CANDIDATE_EXAMPLE),
    ):
        errors = _jsonschema_validate(root / schema_path, root / example_path)
        checks.append({
            "id": check_id,
            "schema": str(schema_path),
            "target": str(example_path),
            "ok": not errors,
            "errors": errors,
        })
    projection = definition_projection_status(projection_root)
    checks.append({
        "id": "definition-store",
        "schema": str(DEFINITION_SCHEMA),
        "target": str(projection_root or definition_projection_dir()),
        "ok": projection["invalid"] == 0,
        "errors": [error for row in projection["records"] for error in row["errors"]],
        "records": projection["total"],
    })
    return {
        "schema_version": "ontology-contract-report-v1",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def lifecycle_snapshot(lineup: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from lawrag.core import batch as batch_mod

    catalog = load_catalog(_pipeline_path())
    validate_catalog(catalog, runner_stages=batch_mod.STAGES)
    batch_lineup = dict(lineup or batch_mod.lineup())
    phase_rows = stages_by_phase(catalog)
    stage_status: dict[str, dict[str, Any]] = {}
    for stage in catalog["stages"]:
        stage_id = str(stage["id"])
        runner_stage = stage.get("runner_stage")
        live = (
            feedback_status()
            if stage_id == "feedback"
            else dict((batch_lineup.get("stages") or {}).get(runner_stage) or {})
        )
        pending = int(live.get("pending") or 0)
        total = int(live.get("total") or 0)
        policy = str(stage["execution_policy"])
        status = "gated" if policy == "manual_only" else "attention" if pending else "ready"
        stage_status[stage_id] = {
            **stage,
            "runner_stage": runner_stage,
            "pending": pending,
            "total": total,
            "status": status,
            "note": live.get("note") or stage["gate"],
            "detail": live.get("detail") or [],
        }

    phases: list[dict[str, Any]] = []
    phase_meta = {str(row["id"]): row for row in catalog["phases"]}
    for phase_id, rows in phase_rows.items():
        values = [stage_status[str(row["id"])] for row in rows]
        pending = sum(row["pending"] for row in values)
        executable = [row for row in values if row["execution_policy"] != "manual_only"]
        phase_status = "attention" if pending else "gated" if not executable else "ready"
        phases.append({
            **phase_meta[phase_id],
            "status": phase_status,
            "pending": pending,
            "stages": [row["id"] for row in values],
        })

    first_pending = next((row for row in stage_status.values() if row["pending"]), None)
    return {
        "schema_version": str(catalog["schema_version"]),
        "pipeline_id": str(catalog["pipeline_id"]),
        "name": str(catalog["name"]),
        "layers": list(catalog["layers"]),
        "phases": phases,
        "stages": stage_status,
        "automatic_runner_stages": list(batch_mod.AUTO_STAGES),
        "explicit_runner_stages": [
            str(row["runner_stage"])
            for row in catalog["stages"]
            if row["execution_policy"] == "explicit"
        ],
        "manual_stages": [
            str(row["id"])
            for row in catalog["stages"]
            if row["execution_policy"] == "manual_only"
        ],
        "next_action": (
            {
                "stage": first_pending["id"],
                "label": first_pending["label"],
                "runner_stage": first_pending.get("runner_stage"),
                "policy": first_pending["execution_policy"],
            }
            if first_pending else None
        ),
        "invariants": list(catalog["invariants"]),
    }
