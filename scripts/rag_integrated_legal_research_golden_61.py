#!/usr/bin/env python3
"""ADR-0114 gold-blind paired LegalClosure evaluation on frozen Golden 61.

The runner deliberately has two storage boundaries:

* ``public-questions-run-001.json`` is the only case fixture opened while the
  two product arms run.
* ``scoring-fixture-run-001.json`` can be opened only after all 61 gold-free
  product captures and their complete provider receipts have been hashed into
  ``product-capture-seal-run-001.json``.

``--preflight-only`` and unit tests never construct an LLM and never make a
provider call.  ``--prepare-fixtures`` is the explicit, offline split step; the
normal run refuses to derive fixtures from the gold-bearing ADR-0091 lock.
``--retrieval-only`` keeps product retrieval unchanged but replaces the
offline semantic judge with exact expected-article containment at the final
``present`` stage.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
from collections import Counter
from copy import deepcopy
import ctypes
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import gc
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import textwrap
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key, _relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core import llm as llm_mod  # noqa: E402
from lawrag.core.rag import (  # noqa: E402
    answer as answer_mod,
    article_reachability,
    index as index_mod,
    integrated_legal_research,
    legalclosure as legalclosure_mod,
    legalclosure_runtime,
)
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0114"
EXPERIMENT_ID = "ADR-0114-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "integrated-seven-layer"
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
MODEL = "claude-haiku-4-5-20251001"
EXPECTED_INPUT_LOCK_SHA256 = (
    "7636cc52ac0bd94a10baa1d75f3f381940981ff86beafa7f7ee91fedf9308452"
)
ADR = ROOT / "docs/adr/ADR-0114-integrated-legal-research-state-machine-golden-61"
INPUT_LOCK = (
    ROOT
    / "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger"
    / "artifacts/input-lock.json"
)
CM_SOURCE = ROOT / "data/review/cm_core_e2e_v2.json"
EXPECTED_CM_SOURCE_SHA256 = (
    "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1"
)
PUBLIC_FIXTURE_NAME = "public-questions-run-001.json"
SCORING_FIXTURE_NAME = "scoring-fixture-run-001.json"
SEAL_NAME = "product-capture-seal-run-001.json"
RUN_ARTIFACT_NAME = "run-001.json"
LEDGER_NAME = "retrieval-stage-ledger-run-001.json"
QUESTION_FORMAT_RECOVERY_ID = "run-001-attempt-003"

CASE_IDS = tuple(
    [f"cm-{number:03d}" for number in range(1, 52)]
    + [f"fsc-hard-{number:03d}" for number in range(1, 11)]
)

STAGE_PLAN: dict[str, tuple[dict[str, Any], ...]] = {
    BASELINE_ARM: (
        {"stage_id": "query-source", "kind": "source", "parent_stage_ids": ()},
        {"stage_id": "a-exact-retrieve", "kind": "retrieve", "parent_stage_ids": ("query-source",)},
        {"stage_id": "a-exact-select", "kind": "select", "parent_stage_ids": ("a-exact-retrieve",)},
        {"stage_id": "b-assertion-retrieve", "kind": "retrieve", "parent_stage_ids": ("query-source",)},
        {"stage_id": "b-assertion-select", "kind": "select", "parent_stage_ids": ("b-assertion-retrieve",)},
        {"stage_id": "c-keyword-retrieve", "kind": "retrieve", "parent_stage_ids": ("query-source",)},
        {"stage_id": "c-keyword-select", "kind": "select", "parent_stage_ids": ("c-keyword-retrieve",)},
        {"stage_id": "abc-union", "kind": "union", "parent_stage_ids": ("a-exact-select", "b-assertion-select", "c-keyword-select")},
        {"stage_id": "d-relation-retrieve", "kind": "expand", "parent_stage_ids": ("abc-union",)},
        {"stage_id": "d-relation-select", "kind": "select", "parent_stage_ids": ("d-relation-retrieve",)},
        {"stage_id": "reference-rescue-expand", "kind": "expand", "parent_stage_ids": ("d-relation-select",)},
        {"stage_id": "required-merge-select", "kind": "select", "parent_stage_ids": ("reference-rescue-expand",)},
        {"stage_id": "scope-filter", "kind": "filter", "parent_stage_ids": ("required-merge-select",)},
        {"stage_id": "present", "kind": "present", "parent_stage_ids": ("scope-filter",)},
    ),
    CANDIDATE_ARM: (
        {"stage_id": "question-source", "kind": "source", "parent_stage_ids": ()},
        {"stage_id": "closed-grounding-retrieve", "kind": "retrieve", "parent_stage_ids": ("question-source",)},
        {"stage_id": "legal-system-route-retrieve", "kind": "retrieve", "parent_stage_ids": ("closed-grounding-retrieve",)},
        {"stage_id": "semantic-card-retrieve", "kind": "retrieve", "parent_stage_ids": ("legal-system-route-retrieve",)},
        {"stage_id": "baseline-floor-union", "kind": "union", "parent_stage_ids": ("semantic-card-retrieve",)},
        {"stage_id": "typed-legal-relation-expand", "kind": "expand", "parent_stage_ids": ("baseline-floor-union",)},
        {"stage_id": "wiki-method-dependency-expand", "kind": "expand", "parent_stage_ids": ("typed-legal-relation-expand",)},
        {"stage_id": "adaptive-gap-retrieve", "kind": "retrieve", "parent_stage_ids": ("wiki-method-dependency-expand",)},
        {"stage_id": "provenance-canonicalize", "kind": "canonicalize", "parent_stage_ids": ("adaptive-gap-retrieve",)},
        {"stage_id": "actor-scope-filter", "kind": "filter", "parent_stage_ids": ("provenance-canonicalize",)},
        {"stage_id": "verified-coverage-select", "kind": "select", "parent_stage_ids": ("actor-scope-filter",)},
        {"stage_id": "compiled-evidence-present", "kind": "present", "parent_stage_ids": ("verified-coverage-select",)},
    ),
}

ERROR_TYPES = (
    "none",
    "retrieval_miss",
    "governing_rule_selection",
    "scope_actor_mismatch",
    "condition_exception",
    "numeric_temporal",
    "authority_or_version",
    "definition_resolution",
    "required_issue_omission",
    "unsupported_inference",
    "judge_or_gold_error",
    "other",
)
JUDGE_SYSTEM = """너는 제품 경로와 완전히 격리된 법률답변 평가자다.
같은 질문에 대한 baseline과 candidate 답변을 기준답변과 비교한다. 표현의 유사성이
아니라 법률 명제, 조건·예외·시점·행위자·수치의 일치를 본다. 검색 좌표는 진단용이며
좌표가 맞았다는 이유만으로 답변을 정답 처리하지 않는다. 근거가 부족한데 가능·불가능을
단정하면 unsupported_definitive_conclusion=true다. 두 제품 답변을 수정하거나 새 답변을
작성하지 말고, 각 답변을 독립 판정한 JSON만 출력한다."""
_ARM_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "unsupported_definitive_conclusion": {"type": "boolean"},
        "failure_type": {"type": "string", "enum": list(ERROR_TYPES)},
        "reason": {"type": "string"},
    },
    "required": [
        "correct", "unsupported_definitive_conclusion", "failure_type", "reason"
    ],
    "additionalProperties": False,
}
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "baseline": deepcopy(_ARM_JUDGE_SCHEMA),
        "candidate": deepcopy(_ARM_JUDGE_SCHEMA),
        "paired_outcome": {
            "type": "string",
            "enum": ["candidate_only", "baseline_only", "both_correct", "both_wrong"],
        },
        "comparison_reason": {"type": "string"},
    },
    "required": ["baseline", "candidate", "paired_outcome", "comparison_reason"],
    "additionalProperties": False,
}


class BoundaryError(RuntimeError):
    """Raised when the product/gold or provider receipt boundary is violated."""


class RuntimeContractError(RuntimeError):
    """Raised when ADR-0114 runtime wiring does not expose its frozen adapter."""


def _drop_file_cache(handle: Any) -> None:
    if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_DONTNEED"):
        try:
            os.posix_fadvise(handle.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        except (AttributeError, OSError):
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        # Golden product captures exceed a gigabyte in aggregate.  Tell Linux
        # that the sequential verification pages are no longer needed so WSL's
        # VM working set does not retain every sealed capture until OOM.
        _drop_file_cache(handle)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=ledger.canonical_json)
    return str(value)


def _json_sha256(value: Any) -> str:
    return ledger.deterministic_sha256(_jsonable(value))


def _json_file_bytes(value: Any) -> bytes:
    return (
        json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _json_file_sha256(value: Any) -> str:
    return hashlib.sha256(_json_file_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        try:
            value = json.load(handle)
        finally:
            _drop_file_cache(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_file_bytes(value)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    with temporary.open("wb", buffering=0) as handle:
        view = memoryview(payload)
        while view:
            written = handle.write(view)
            view = view[written:]
        os.fsync(handle.fileno())
        _drop_file_cache(handle)
    os.replace(temporary, path)


def _write_json_once_or_same(path: Path, value: Any) -> None:
    """Recovery-safe immutable write for a derived final artifact."""

    payload = _json_file_bytes(value)
    if path.exists():
        if (
            path.stat().st_size != len(payload)
            or _sha256(path) != hashlib.sha256(payload).hexdigest()
        ):
            raise BoundaryError(f"existing derived artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    with temporary.open("wb", buffering=0) as handle:
        view = memoryview(payload)
        while view:
            written = handle.write(view)
            view = view[written:]
        os.fsync(handle.fileno())
        _drop_file_cache(handle)
    os.replace(temporary, path)


def _write_question_result(path: Path, text: str) -> None:
    """Atomically replace only the generated TODO template, or verify recovery."""

    payload = text.encode("utf-8")
    if path.exists():
        current = path.read_bytes()
        if current == payload:
            return
        if b"- \xec\x8b\xa4\xed\x96\x89 \xec\x8b\x9c\xea\xb0\x81: TODO" not in current:
            raise BoundaryError(f"completed question artifact differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    with temporary.open("wb", buffering=0) as handle:
        view = memoryview(payload)
        while view:
            written = handle.write(view)
            view = view[written:]
        os.fsync(handle.fileno())
        _drop_file_cache(handle)
    os.replace(temporary, path)


def _completed_question_result(path: Path, case_id: str) -> bool:
    """Recognize only this runner's atomically completed question receipt."""

    if not path.is_file():
        return False
    with path.open("rb", buffering=0) as handle:
        head = handle.read(4096).decode("utf-8", errors="replace")
        _drop_file_cache(handle)
    return (
        head.startswith("# 질문 ")
        and f"— {case_id}\n" in head
        and "product capture 상태: `sealed exact`" in head
        and "- 실행 시각: TODO" not in head
    )


def _release_process_memory() -> None:
    """Return per-case large JSON arenas to glibc during streaming finalize."""

    gc.collect()
    try:
        trim = ctypes.CDLL(None).malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        trim(0)
    except (AttributeError, OSError):
        pass


def _acquire_run_lock(adr: Path):
    """Hold one process-wide ADR run lock until the returned handle is closed."""

    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - official runner is Linux/WSL
        raise BoundaryError("ADR-0114 runner requires an OS advisory file lock") from exc
    path = adr / "artifacts" / f".{RUN_ID}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise BoundaryError(f"another ADR-0114 {RUN_ID} process is active") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "acquired_at": _now()}))
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def _self_hash(value: Mapping[str, Any], field: str) -> str:
    return _json_sha256({key: deepcopy(item) for key, item in value.items() if key != field})


def _percentile(values: Iterable[float], ratio: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    return rows[min(len(rows) - 1, round((len(rows) - 1) * ratio))]


def _artifact_paths(adr: Path = ADR) -> dict[str, Path]:
    artifacts = adr / "artifacts"
    return {
        "public": artifacts / PUBLIC_FIXTURE_NAME,
        "scoring": artifacts / SCORING_FIXTURE_NAME,
        "captures": artifacts / "product-captures" / RUN_ID,
        "judges": artifacts / "judge-receipts" / RUN_ID,
        "finalize_shards": artifacts / "finalize-shards" / RUN_ID,
        "seal": artifacts / SEAL_NAME,
        "run": artifacts / RUN_ARTIFACT_NAME,
        "ledger": artifacts / LEDGER_NAME,
        "retrieval_only": artifacts / f"retrieval-only-{RUN_ID}.json",
    }


def _forbid_product_gold(value: Any, path: str = "product") -> None:
    """Reject gold/reference-bearing fields from any product-side artifact."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key)
            lowered = name.lower()
            if name not in {"gold_visible_to_product"} and (
                "gold" in lowered
                or name in {"reference_answer", "expected_articles", "current_articles"}
            ):
                raise BoundaryError(f"gold-bearing field in product artifact: {path}.{name}")
            _forbid_product_gold(child, f"{path}.{name}")
    elif isinstance(value, (list, tuple)):
        for number, child in enumerate(value):
            _forbid_product_gold(child, f"{path}[{number}]")


def _expected_case_ids() -> list[str]:
    return list(CASE_IDS)


def _required_companions(
    payload: Mapping[str, Any], cm_source: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    locked = {str(row.get("id") or ""): row for row in payload.get("cases") or ()}
    companions: dict[str, list[dict[str, Any]]] = {}
    for source_case in cm_source.get("cases") or ():
        case_id = str(source_case.get("id") or "")
        if case_id not in locked:
            continue
        expected_source_hash = str(locked[case_id].get("source_case_sha256") or "")
        if expected_source_hash and _json_sha256(source_case) != expected_source_hash:
            raise ValueError(f"CM source case changed after ADR-0091 freeze: {case_id}")
        rows = []
        for row in source_case.get("required_companions") or ():
            if (
                row.get("corpus_status") != "present"
                or row.get("evidence_role") != "required_companion"
            ):
                continue
            node = row.get("node")
            if isinstance(node, str) and node.isdigit():
                node = int(node)
            if isinstance(node, bool) or not isinstance(node, int):
                raise ValueError(f"invalid required companion node: {case_id}/{node}")
            rows.append({
                "law": row.get("law"),
                "article": row.get("article"),
                "doc_id": str(row["doc_id"]),
                "node": node,
                "corpus_status": row.get("corpus_status"),
                "evidence_role": row.get("evidence_role"),
                "authority_as_of": row.get("authority_as_of"),
                "coordinate_scope": row.get("coordinate_scope"),
                "coordinate_key": row.get("coordinate_key"),
            })
        if rows:
            companions[case_id] = rows
    if len(companions) != 14 or sum(map(len, companions.values())) != 22:
        raise ValueError(
            "CM v2 required_companions must be frozen 14 cases / 22 coordinates"
        )
    return companions


def split_input_lock(
    payload: Mapping[str, Any], cm_source: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create physically separate question-only and offline scoring payloads."""
    cases = list(payload.get("cases") or ())
    ids = [str(case.get("id") or "") for case in cases]
    if ids != _expected_case_ids():
        raise ValueError("ADR-0091 input-lock must contain frozen CM51+FSC10 order")
    gold_total = sum(len(case.get("gold_articles") or ()) for case in cases)
    if len(cases) != 61 or gold_total != 90:
        raise ValueError(f"expected 61 cases / 90 decisive coordinates, got {len(cases)} / {gold_total}")
    companions = _required_companions(payload, cm_source)
    public = {
        "schema_version": "adr-0114-public-questions-v1",
        "source_input_lock_sha256": EXPECTED_INPUT_LOCK_SHA256,
        "gold_visible_to_product": False,
        "selection_rule": "ADR-0091 frozen order; CM51 + FSC10; no exclusions",
        "cases": [
            {
                "number": int(case["number"]),
                "case_id": str(case["id"]),
                "suite": str(case["suite"]),
                "question": str(case["question"]),
                "material": case.get("material"),
                "mode": case.get("mode"),
                "answer_as_of": case.get("answer_as_of"),
                "current_as_of": case.get("current_as_of"),
            }
            for case in cases
        ],
    }
    scoring = {
        "schema_version": "adr-0114-offline-scoring-fixture-v1",
        "source_input_lock_sha256": EXPECTED_INPUT_LOCK_SHA256,
        "product_access": "forbidden-before-valid-product-seal",
        "cases": [
            {
                "number": int(case["number"]),
                "case_id": str(case["id"]),
                "reference_answer": str(case.get("reference_answer") or ""),
                "gold_articles": deepcopy(list(case.get("gold_articles") or ())),
                "required_companions": deepcopy(companions.get(str(case["id"]), [])),
            }
            for case in cases
        ],
    }
    _forbid_product_gold(public)
    if any("question" in row for row in scoring["cases"]):
        raise BoundaryError("scoring fixture must not duplicate product questions")
    return public, scoring


def prepare_fixtures(
    input_lock: Path = INPUT_LOCK,
    cm_source: Path = CM_SOURCE,
    public_path: Path | None = None,
    scoring_path: Path | None = None,
) -> dict[str, Any]:
    paths = _artifact_paths()
    public_path = public_path or paths["public"]
    scoring_path = scoring_path or paths["scoring"]
    actual = _sha256(input_lock)
    if actual != EXPECTED_INPUT_LOCK_SHA256:
        raise ValueError(f"ADR-0091 input-lock hash mismatch: {actual}")
    cm_actual = _sha256(cm_source)
    if cm_actual != EXPECTED_CM_SOURCE_SHA256:
        raise ValueError(f"CM v2 source hash mismatch: {cm_actual}")
    public, scoring = split_input_lock(
        _read_json(input_lock), _read_json(cm_source)
    )
    _write_json(public_path, public)
    _write_json(scoring_path, scoring)
    return {
        "status": "prepared",
        "cases": 61,
        "input_lock_sha256": actual,
        "cm_source_sha256": cm_actual,
        "public_path": str(public_path),
        "public_sha256": _sha256(public_path),
        "scoring_path": str(scoring_path),
        "scoring_sha256": _sha256(scoring_path),
        "provider_calls": 0,
    }


def fixture_integrity_receipt(
    *, input_lock: Path, cm_source: Path, public_path: Path,
    scoring_path: Path,
) -> dict[str, Any]:
    """Recompute both canonical fixtures without returning gold to product code."""
    input_sha = _sha256(input_lock)
    cm_sha = _sha256(cm_source)
    if input_sha != EXPECTED_INPUT_LOCK_SHA256:
        raise BoundaryError(f"ADR-0091 input-lock hash mismatch: {input_sha}")
    if cm_sha != EXPECTED_CM_SOURCE_SHA256:
        raise BoundaryError(f"CM v2 source hash mismatch: {cm_sha}")
    public, scoring = split_input_lock(
        _read_json(input_lock), _read_json(cm_source)
    )
    expected_public_sha = _json_file_sha256(public)
    expected_scoring_sha = _json_file_sha256(scoring)
    public_exact = (
        public_path.is_file()
        and _sha256(public_path) == expected_public_sha
        and _read_json(public_path) == public
    )
    scoring_exact = (
        scoring_path.is_file()
        and _sha256(scoring_path) == expected_scoring_sha
        and _read_json(scoring_path) == scoring
    )
    return {
        "input_lock_sha256": input_sha,
        "cm_source_sha256": cm_sha,
        "canonical_public_sha256": expected_public_sha,
        "canonical_scoring_sha256": expected_scoring_sha,
        "public_exact": public_exact,
        "scoring_exact": scoring_exact,
        "ready": public_exact and scoring_exact,
        "cases": 61,
        "decisive_coordinates": 90,
        "required_companion_cases": 14,
        "required_companion_coordinates": 22,
    }


def _manifest_stage_plan(manifest: Mapping[str, Any]) -> dict[str, tuple[dict[str, Any], ...]]:
    raw = (((manifest.get("design") or {}).get("retrieval_stage_plan") or {})
           .get("stages_by_arm") or {})
    out: dict[str, tuple[dict[str, Any], ...]] = {}
    for arm in ARMS:
        out[arm] = tuple({
            "stage_id": str(row["stage_id"]),
            "kind": str(row["kind"]),
            "parent_stage_ids": tuple(row.get("parent_stage_ids") or ()),
        } for row in raw.get(arm) or ())
    return out


def baseline_raw_stage_contract() -> dict[str, Any]:
    """Statically verify the raw LegalClosure trace before an experiment call.

    The baseline adapter consumes the runtime's native ``stage_ledger``.  A
    hand-built approximation would make the frozen lifecycle incomparable, so
    preflight refuses to proceed unless every literal ``trace.stage`` call in
    the emitting function exactly matches the declared ADR plan.
    """
    try:
        source = textwrap.dedent(inspect.getsource(legalclosure_mod._trace_reachability))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError) as exc:
        return {
            "ready": False,
            "reason": f"cannot inspect LegalClosure raw stage emitter: {type(exc).__name__}: {exc}",
            "observed": [],
        }
    observed_rows: list[tuple[int, dict[str, Any]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "stage"
            and isinstance(function.value, ast.Name)
            and function.value.id == "trace"
        ):
            continue
        if len(node.args) < 2:
            return {"ready": False, "reason": "non-literal trace.stage call", "observed": []}
        try:
            stage_id = ast.literal_eval(node.args[0])
            kind = ast.literal_eval(node.args[1])
            parents: tuple[str, ...] = ()
            for keyword in node.keywords:
                if keyword.arg == "parent_stage_ids":
                    parents = tuple(ast.literal_eval(keyword.value))
                    break
        except (ValueError, TypeError, SyntaxError):
            return {"ready": False, "reason": "non-literal trace.stage call", "observed": []}
        if not isinstance(stage_id, str) or not isinstance(kind, str):
            return {"ready": False, "reason": "non-string trace stage declaration", "observed": []}
        observed_rows.append((node.lineno, {
            "stage_id": stage_id,
            "kind": kind,
            "parent_stage_ids": parents,
        }))
    observed = tuple(row for _, row in sorted(observed_rows, key=lambda item: item[0]))
    ready = observed == STAGE_PLAN[BASELINE_ARM]
    return {
        "ready": ready,
        "reason": "" if ready else "runtime trace.stage lifecycle differs from frozen baseline plan",
        "observed": [
            {**row, "parent_stage_ids": list(row["parent_stage_ids"])}
            for row in observed
        ],
    }


def runtime_adapter_contract(retrieve: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Inspect, but never call, the frozen integrated retrieval adapter."""
    retrieve = retrieve or legalclosure_runtime.retrieve
    parameters = inspect.signature(retrieve).parameters
    required = ("integrated_research_enabled", "integrated_cap", "baseline_result")
    missing = [name for name in required if name not in parameters]
    baseline_capture = baseline_raw_stage_contract()
    return {
        "ready": not missing and baseline_capture["ready"],
        "missing": missing,
        "baseline_result_sharing": "baseline_result" in parameters,
        "baseline_raw_stage_capture": baseline_capture,
        "required_call": (
            "legalclosure_runtime.retrieve(..., cap=20, "
            "integrated_research_enabled=True, integrated_cap=32, "
            "baseline_result=<current-baseline-retrieval>)"
        ),
    }


def preflight_receipt(
    *, adr: Path = ADR, input_lock: Path = INPUT_LOCK,
    cm_source: Path = CM_SOURCE,
    retrieve: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Read-only validation.  It intentionally does not instantiate ``LLM``."""
    manifest_path = adr / "실험/manifest.json"
    manifest = _read_json(manifest_path)
    input_sha = _sha256(input_lock)
    paths = _artifact_paths(adr)
    fixture = fixture_integrity_receipt(
        input_lock=input_lock,
        cm_source=cm_source,
        public_path=paths["public"],
        scoring_path=paths["scoring"],
    )
    runtime = runtime_adapter_contract(retrieve)
    manifest_plan = _manifest_stage_plan(manifest)
    lexicon_compile_disabled = (
        os.environ.get("RAG_LEXICON_COMPILE_MISSING", "0") != "1"
    )
    receipt = {
        "status": "ready" if (
            input_sha == EXPECTED_INPUT_LOCK_SHA256
            and manifest.get("dataset", {}).get("sha256") == EXPECTED_INPUT_LOCK_SHA256
            and manifest_plan == STAGE_PLAN
            and runtime["ready"]
            and fixture["ready"]
            and lexicon_compile_disabled
        ) else "blocked",
        "provider_calls": 0,
        "llm_constructed": False,
        "cases": len(manifest.get("questions") or ()),
        "input_lock_sha256": input_sha,
        "input_lock_expected": EXPECTED_INPUT_LOCK_SHA256,
        "manifest_dataset_hash_matches": (
            manifest.get("dataset", {}).get("sha256") == EXPECTED_INPUT_LOCK_SHA256
        ),
        "stage_plan_matches": manifest_plan == STAGE_PLAN,
        "runtime_adapter": runtime,
        "lexicon_compile_missing_disabled": lexicon_compile_disabled,
        "fixtures": {
            "public_exists": paths["public"].exists(),
            "scoring_exists": paths["scoring"].exists(),
            "normal_run_requires_prepared_fixtures": True,
            "integrity": fixture,
        },
        "boundary": {
            "product_input": PUBLIC_FIXTURE_NAME,
            "offline_scoring_input": SCORING_FIXTURE_NAME,
            "gold_open_gate": SEAL_NAME,
        },
        "expected_artifacts": [
            PUBLIC_FIXTURE_NAME,
            SCORING_FIXTURE_NAME,
            "product-captures/run-001/<case-id>.json",
            SEAL_NAME,
            "judge-receipts/run-001/<case-id>.json",
            LEDGER_NAME,
            RUN_ARTIFACT_NAME,
            "실험/질문-NNN-<case-id>.md",
        ],
    }
    if receipt["cases"] != 61:
        receipt["status"] = "blocked"
    return receipt


class RecordingLLM:
    """Haiku-only facade preserving exact request and provider raw exchange."""

    def __init__(self, real: Any):
        self.real = real
        self.model = MODEL
        self.backend = str(getattr(real, "backend", ""))
        self.log = real.log
        self.audit: list[dict[str, Any]] = []

    def structured(
        self, kind: str, system: str, user: str, schema: dict[str, Any],
        max_tokens: int = 16000, effort: str = "high", images=None,
        model: str | None = None,
    ) -> Any:
        requested = model or MODEL
        if requested != MODEL:
            raise RuntimeError(f"product/evaluator model policy mismatch: {requested}")
        before = len(self.real.log)
        output = None
        raised: BaseException | None = None
        try:
            output = self.real.structured(
                kind, system, user, schema, max_tokens=max_tokens,
                effort=effort, images=images, model=MODEL,
            )
            return output
        except BaseException as exc:  # receipt is required even on provider failure
            raised = exc
            raise
        finally:
            exchange = self.real.log[before] if len(self.real.log) > before else None
            provider = exchange.dump() if exchange is not None else {
                "model": "", "raw_response": "", "error": (
                    f"{type(raised).__name__}: {raised}" if raised else "missing provider exchange"
                ),
            }
            if exchange is not None:
                provider["parsed"] = _jsonable(getattr(exchange, "parsed", None))
            provider["backend"] = self.backend
            actual_model = str(provider.get("model") or "")
            if exchange is not None and actual_model != MODEL:
                provider["model_policy_error"] = f"expected {MODEL}, got {actual_model}"
            self.audit.append({
                "kind": kind,
                "class": "offline_evaluator" if kind.startswith("adr0114.judge") else "product",
                "requested_model": requested,
                "backend": self.backend,
                "system": system,
                "user": user,
                "schema": deepcopy(schema),
                "max_tokens": max_tokens,
                "effort": effort,
                "provider": provider,
                "structured_output": _jsonable(output),
            })


def _usage(calls: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "calls": len(calls),
        "input_tokens": sum(int((call.get("provider") or {}).get("usage", {}).get("input_tokens", 0)) for call in calls),
        "output_tokens": sum(int((call.get("provider") or {}).get("usage", {}).get("output_tokens", 0)) for call in calls),
        "provider_duration_ms": sum(int((call.get("provider") or {}).get("dur_ms", 0)) for call in calls),
        "errors": sum(bool((call.get("provider") or {}).get("error")) for call in calls),
    }


def _usage_add(*values: Mapping[str, Any]) -> dict[str, int]:
    keys = ("calls", "input_tokens", "output_tokens", "provider_duration_ms", "errors")
    return {key: sum(int(value.get(key) or 0) for value in values) for key in keys}


def _section_rows(sections: Sequence[answer_mod.Section]) -> list[dict[str, Any]]:
    return [
        {
            "rank": number,
            "doc_id": str(section.doc_id),
            "node": int(section.node) if section.node is not None else None,
            "doc": section.doc,
            "path": section.path,
            "page": section.page,
            "kind": section.kind,
            "matched": section.matched,
            "text": section.text,
            "ref_src": deepcopy(section.ref_src),
            "scope_out": bool(section.scope_out),
            "edges": deepcopy(section.edges),
            "legal_meta": deepcopy(section.legal_meta),
            "definition_context": deepcopy(section.definition_context),
        }
        for number, section in enumerate(sections, 1)
    ]


def _coordinates(rows: Iterable[Any]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for row in rows:
        if isinstance(row, Mapping):
            doc_id, node = row.get("doc_id"), row.get("node")
        else:
            doc_id, node = getattr(row, "doc_id", None), getattr(row, "node", None)
        if doc_id and isinstance(node, int) and not isinstance(node, bool):
            out.append((str(doc_id), int(node)))
    return out


def _stage_rows(capture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(row["stage_id"]): row for row in capture.get("stages") or ()}


def _rows_to_coordinates(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, int]]:
    return [(str(row["doc_id"]), int(row["node"])) for row in rows]


def _canonical_set(canonicalize: Callable[[tuple[str, int]], tuple[str, int]], values: Iterable[Any]) -> set[tuple[str, int]]:
    return {canonicalize(value) for value in _coordinates(values)}


def _record_exact_stage(
    recorder: ledger.StageLedgerRecorder,
    canonicalize: Callable[[tuple[str, int]], tuple[str, int]],
    spec: Mapping[str, Any],
    after: Iterable[tuple[str, int]],
    parent_after: Iterable[tuple[str, int]],
    reason: str,
) -> None:
    after_rows = list(after)
    before_set = _canonical_set(canonicalize, ({"doc_id": d, "node": n} for d, n in parent_after))
    after_set = _canonical_set(canonicalize, ({"doc_id": d, "node": n} for d, n in after_rows))
    discard = [(coordinate, reason) for coordinate in sorted(before_set - after_set)]
    recorder.record_stage(
        str(spec["stage_id"]), str(spec["kind"]), after_rows,
        parent_stage_ids=tuple(spec["parent_stage_ids"]),
        discard_reasons=discard,
    )


def _raw_stage_after(raw_capture: Mapping[str, Any], stage_id: str) -> list[tuple[str, int]]:
    raw = raw_capture.get("stage_ledger") or raw_capture
    row = next((item for item in raw.get("stages") or () if item.get("stage_id") == stage_id), None)
    if row is None:
        raise BoundaryError(f"baseline raw reachability stage missing: {stage_id}")
    return _rows_to_coordinates(row.get("after") or ())


def baseline_stage_capture(
    index: Any, case_id: str, sections: Sequence[answer_mod.Section], meta: Mapping[str, Any]
) -> dict[str, Any]:
    """Preserve LegalClosure's exact lifecycle; lossy stage folding is forbidden."""
    raw = meta.get("article_reachability")
    if not isinstance(raw, Mapping):
        raise BoundaryError("baseline article_reachability product capture is missing")
    article_reachability.validate_capture(raw)
    capture = raw.get("stage_ledger")
    if not isinstance(capture, Mapping):
        raise BoundaryError("baseline raw stage_ledger is missing")
    validated = validate_declared_capture(capture, case_id, BASELINE_ARM)
    if _present_coordinates(validated) != set(
        ledger.index_article_root_canonicalizer(index)(coordinate)
        for coordinate in _coordinates(sections)
    ):
        raise BoundaryError("baseline present stage differs from returned evidence")
    return validated


def validate_declared_capture(capture: Mapping[str, Any], case_id: str, arm_id: str) -> dict[str, Any]:
    ledger.validate_capture(capture)
    if capture.get("case_id") != case_id or capture.get("arm_id") != arm_id:
        raise BoundaryError("candidate stage capture case/arm identity mismatch")
    observed = tuple(
        {
            "stage_id": str(row["stage_id"]),
            "kind": str(row["kind"]),
            "parent_stage_ids": tuple(row.get("parent_stage_ids") or ()),
        }
        for row in capture.get("stages") or ()
    )
    if observed != STAGE_PLAN[arm_id]:
        raise BoundaryError(f"{arm_id} runtime stages differ from frozen ADR-0114 plan")
    if capture.get("gold_visible_to_product") is not False:
        raise BoundaryError("runtime stage capture exposed gold")
    return deepcopy(dict(capture))


def candidate_stage_capture(meta: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    integrated = meta.get("integrated_research") or {}
    candidates = (
        integrated.get("stage_capture") if isinstance(integrated, Mapping) else None,
        integrated.get("retrieval_stage_capture") if isinstance(integrated, Mapping) else None,
        integrated.get("stage_ledger") if isinstance(integrated, Mapping) else None,
    )
    capture = next((row for row in candidates if isinstance(row, Mapping)), None)
    if capture is None:
        raise BoundaryError("candidate metadata needs integrated_research.stage_capture")
    return validate_declared_capture(capture, case_id, CANDIDATE_ARM)


def skipped_stage_capture(index: Any, case_id: str, arm_id: str, reason: str) -> dict[str, Any]:
    recorder = ledger.StageLedgerRecorder(
        case_id, arm_id, ledger.index_article_root_canonicalizer(index)
    )
    for number, spec in enumerate(STAGE_PLAN[arm_id]):
        if number == 0:
            recorder.record_stage(spec["stage_id"], spec["kind"], [])
        else:
            recorder.record_stage(
                spec["stage_id"], spec["kind"],
                parent_stage_ids=spec["parent_stage_ids"],
                executed=False, skip_reason=reason,
            )
    return recorder.capture()


def call_candidate_retrieve(
    retrieve: Callable[..., Any], index: Any, question: str, *, llm: Any,
    reachability_trace: Any, baseline_result: tuple[Any, Any] | None,
) -> tuple[Any, Any, bool]:
    """Small adapter isolating the ADR-0114 expected runtime signature."""
    contract = runtime_adapter_contract(retrieve)
    if not contract["ready"]:
        raise RuntimeContractError(
            f"integrated runtime parameters missing: {contract['missing']}"
        )
    kwargs: dict[str, Any] = {
        "llm": llm,
        "assertion_llm": llm,
        "cap": 20,
        "integrated_research_enabled": True,
        "integrated_cap": 32,
        "shortcut_enabled": False,
        "feedback_enabled": False,
        "reachability_trace": reachability_trace,
    }
    shared = bool(baseline_result is not None and contract["baseline_result_sharing"])
    if shared:
        kwargs["baseline_result"] = baseline_result
    sections, meta = retrieve(index, question, **kwargs)
    return sections, meta, shared


def _answer_payload(result: answer_mod.Answer) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "answerable": bool(result.answerable),
        "error": result.error,
        "refs": _jsonable(result.refs),
        "wiki": _jsonable(result.wiki),
    }


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def integrated_execution_metrics(
    index: Any, sections: Sequence[answer_mod.Section], meta: Mapping[str, Any]
) -> dict[str, Any]:
    integrated = meta.get("integrated_research")
    if not isinstance(integrated, Mapping) or integrated.get("enabled") is not True:
        raise BoundaryError("candidate integrated_research metadata is missing or disabled")
    total_ms = integrated.get("elapsed_ms")
    if isinstance(total_ms, bool) or not isinstance(total_ms, (int, float)) or total_ms < 0:
        raise BoundaryError("integrated_research.elapsed_ms is required")
    planner_receipts = ((integrated.get("planner") or {}).get("receipts") or ())
    planner_provider_ms = sum(
        float((receipt.get("provider") or {}).get("dur_ms") or 0)
        for receipt in planner_receipts if isinstance(receipt, Mapping)
    )
    deterministic_ms = integrated.get("deterministic_planning_ms")
    if (
        isinstance(deterministic_ms, bool)
        or not isinstance(deterministic_ms, (int, float))
        or deterministic_ms < 0
    ):
        raise BoundaryError(
            "integrated_research.deterministic_planning_ms is required"
        )

    closed_id_violations: list[str] = []
    for section in sections:
        view = index.docs.get(str(section.doc_id))
        if view is None or section.node not in view.by_id:
            closed_id_violations.append(f"selected:{section.doc_id}:{section.node}")
    for row in _walk_mappings(integrated.get("entry_plans") or ()):
        instrument_id = row.get("instrument_id")
        node_id = row.get("node_id")
        if instrument_id and instrument_id not in index.docs:
            closed_id_violations.append(f"entry-instrument:{instrument_id}")
        if instrument_id and isinstance(node_id, int):
            view = index.docs.get(str(instrument_id))
            if view is None or node_id not in view.by_id:
                closed_id_violations.append(f"entry-node:{instrument_id}:{node_id}")

    generation_violations: list[str] = []
    if integrated.get("authority_generation") != index.authority_generation:
        generation_violations.append("authority_generation")
    if integrated.get("authority_as_of") != index.authority_as_of:
        generation_violations.append("authority_as_of")

    verified_count = 0
    evidence_violations: list[str] = []
    for section in sections:
        lifecycle = ((section.legal_meta or {}).get("integrated_research") or {})
        states = set(lifecycle.get("states") or ())
        if "VERIFIED_EVIDENCE" in states:
            verified_count += 1
        else:
            evidence_violations.append(f"unverified-present:{section.doc_id}:{section.node}")
        if lifecycle.get("direct_conclusion_allowed") is not False:
            evidence_violations.append(f"direct-conclusion:{section.doc_id}:{section.node}")
    compilation = integrated.get("final_compilation") or {}
    evidence_violations.extend(
        f"compiler-unverified:{value}"
        for value in compilation.get("unverified_coordinates") or ()
    )
    evidence_violations.extend(
        f"missing-mandatory:{value}"
        for value in compilation.get("missing_mandatory_coordinates") or ()
    )
    if integrated.get("direct_conclusion_allowed") is not False:
        evidence_violations.append("integrated-direct-conclusion")
    return {
        "integrated_total_ms": round(float(total_ms), 3),
        "planner_provider_ms": round(planner_provider_ms, 3),
        "deterministic_planning_ms": round(float(deterministic_ms), 3),
        "closed_id_violations": sorted(set(closed_id_violations)),
        "closed_id_violation_count": len(set(closed_id_violations)),
        "generation_violations": sorted(set(generation_violations)),
        "generation_violation_count": len(set(generation_violations)),
        "verified_evidence_violations": sorted(set(evidence_violations)),
        "verified_evidence_violation_count": len(set(evidence_violations)),
        "verified_evidence_count": verified_count,
        "presented_evidence_count": len(sections),
        "verified_rate": round(verified_count / len(sections), 6) if sections else 0.0,
        "runtime_error_count": len(integrated.get("errors") or ()),
        "fallback": str(integrated.get("fallback") or ""),
    }


def _execute_arm(
    *, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any,
    baseline_result: tuple[Any, Any] | None = None,
) -> tuple[dict[str, Any], tuple[Any, Any] | None]:
    recording = RecordingLLM(real_llm)
    sections: list[answer_mod.Section] = []
    meta: dict[str, Any] = {}
    stage_capture: dict[str, Any]
    shared = False
    started = time.perf_counter()
    retrieval_started = started
    retrieval_wall_ms = 0.0
    retrieval_call_count = 0
    execution_metrics: dict[str, Any] = {}
    error = ""
    try:
        trace = article_reachability.ArticleReachabilityTrace(index, case["case_id"], arm_id)
        if arm_id == BASELINE_ARM:
            sections, meta = legalclosure_runtime.retrieve(
                index, case["question"], llm=recording, assertion_llm=recording,
                cap=20, shortcut_enabled=False, feedback_enabled=False,
                graph_enabled=False, semantic_graph_enabled=False,
                reachability_trace=trace,
            )
            stage_capture = baseline_stage_capture(index, case["case_id"], sections, meta)
        else:
            sections, meta, shared = call_candidate_retrieve(
                legalclosure_runtime.retrieve, index, case["question"],
                llm=recording, reachability_trace=trace,
                baseline_result=baseline_result,
            )
            if len(sections) > 32:
                raise BoundaryError(f"candidate evidence cap exceeded: {len(sections)}")
            stage_capture = candidate_stage_capture(meta, case["case_id"])
            execution_metrics = integrated_execution_metrics(index, sections, meta)
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        if arm_id == BASELINE_ARM:
            execution_metrics = {
                "integrated_total_ms": 0.0,
                "planner_provider_ms": 0.0,
                "deterministic_planning_ms": 0.0,
                "closed_id_violations": [],
                "closed_id_violation_count": 0,
                "generation_violations": [],
                "generation_violation_count": 0,
                "verified_evidence_violations": [],
                "verified_evidence_violation_count": 0,
                "verified_evidence_count": 0,
                "presented_evidence_count": len(sections),
                "verified_rate": 0.0,
                "measurement_note": (
                    "baseline has current-source annotations but no ADR-0114 "
                    "source-span verification receipt"
                ),
            }
        answer_started = time.perf_counter()
        answer = answer_mod.synthesize(recording, case["question"], list(sections))
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 3)
        answer_payload = _answer_payload(answer)
        reusable = (deepcopy(list(sections)), deepcopy(meta))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        stage_capture = skipped_stage_capture(index, case["case_id"], arm_id, error)
        answer_ms = 0.0
        answer_payload = {
            "answer": "", "answerable": False, "error": error, "refs": [], "wiki": []
        }
        reusable = None
        execution_metrics = {
            "deterministic_planning_ms": 0.0,
            "closed_id_violation_count": 0,
            "generation_violation_count": 0,
            "verified_evidence_violation_count": 0,
            "verified_evidence_count": 0,
            "presented_evidence_count": len(sections),
            "verified_rate": 0.0,
            "measurement_error": error,
        }
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    payload = {
        "arm_id": arm_id,
        "status": "error" if error else "complete",
        "error": error,
        "baseline_retrieval_shared": shared,
        "retrieval": {
            "sections": _section_rows(sections),
            "meta": _jsonable(meta),
            "stage_capture": stage_capture,
        },
        "execution_metrics": execution_metrics,
        "answer": answer_payload,
        "provider_calls": deepcopy(recording.audit),
        "retrieval_provider_calls": deepcopy(recording.audit[:retrieval_call_count]),
        "answer_provider_calls": deepcopy(recording.audit[retrieval_call_count:]),
        "usage": _usage(recording.audit),
        "wall_ms": wall_ms,
        "retrieval_wall_ms": retrieval_wall_ms,
        "answer_wall_ms": answer_ms,
    }
    return payload, reusable


def execute_product_case(
    index: Any, case: Mapping[str, Any], real_llm: Any, corpus_total: int,
    corpus_fingerprint: str, run_environment_hash: str,
) -> dict[str, Any]:
    baseline, baseline_result = _execute_arm(
        arm_id=BASELINE_ARM, index=index, case=case, real_llm=real_llm
    )
    candidate, _ = _execute_arm(
        arm_id=CANDIDATE_ARM, index=index, case=case, real_llm=real_llm,
        baseline_result=baseline_result,
    )
    baseline["accounting"] = {
        "marginal": {
            "usage": deepcopy(baseline["usage"]),
            "wall_ms": baseline["wall_ms"],
        },
        "inclusive": {
            "usage": deepcopy(baseline["usage"]),
            "wall_ms": baseline["wall_ms"],
        },
        "shared_baseline_retrieval_added": False,
        "baseline_answer_added": False,
    }
    shared_usage = (
        _usage(baseline["retrieval_provider_calls"])
        if candidate["baseline_retrieval_shared"] else _usage([])
    )
    shared_wall = (
        float(baseline["retrieval_wall_ms"])
        if candidate["baseline_retrieval_shared"] else 0.0
    )
    candidate["accounting"] = {
        "marginal": {
            "usage": deepcopy(candidate["usage"]),
            "wall_ms": candidate["wall_ms"],
        },
        "inclusive": {
            "usage": _usage_add(candidate["usage"], shared_usage),
            "wall_ms": round(float(candidate["wall_ms"]) + shared_wall, 3),
        },
        "shared_baseline_retrieval_added": bool(candidate["baseline_retrieval_shared"]),
        "shared_baseline_retrieval_usage": shared_usage,
        "shared_baseline_retrieval_wall_ms": shared_wall,
        "baseline_answer_added": False,
        "criteria_accounting": "inclusive",
    }
    value = {
        "schema_version": "adr-0114-gold-free-product-capture-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "number": int(case["number"]),
        "case_id": str(case["case_id"]),
        "suite": str(case["suite"]),
        "question": str(case["question"]),
        "model": MODEL,
        "gold_visible_to_product": False,
        "authority_generation": str(index.authority_generation),
        "authority_as_of": str(index.authority_as_of),
        "corpus_fingerprint": corpus_fingerprint,
        "run_environment_hash": run_environment_hash,
        "corpus_article_roots": int(corpus_total),
        "arms": {BASELINE_ARM: baseline, CANDIDATE_ARM: candidate},
        "captured_at": _now(),
        "complete": True,
    }
    _forbid_product_gold(value)
    value["capture_sha256"] = _self_hash(value, "capture_sha256")
    validate_product_capture(value)
    return value


def _validate_provider_call(call: Mapping[str, Any], *, call_class: str) -> None:
    expected_class = "offline_evaluator" if call_class == "offline evaluator" else "product"
    if call.get("class") != expected_class:
        raise BoundaryError(f"{call_class} receipt class mismatch")
    if call.get("requested_model") != MODEL:
        raise BoundaryError(f"non-Haiku {call_class} call requested")
    if call.get("backend") != "anthropic":
        raise BoundaryError(f"{call_class} backend must be anthropic")
    provider = call.get("provider")
    if not isinstance(provider, Mapping):
        raise BoundaryError(f"{call_class} provider receipt is missing")
    if provider.get("model") != MODEL:
        raise BoundaryError(f"non-Haiku {call_class} provider receipt")
    if provider.get("backend") != "anthropic":
        raise BoundaryError(f"{call_class} provider receipt backend must be anthropic")
    for required in ("raw_response", "usage", "dur_ms", "error"):
        if required not in provider:
            raise BoundaryError(f"{call_class} provider receipt missing {required}")
    if not isinstance(provider.get("usage"), Mapping):
        raise BoundaryError(f"{call_class} provider usage must be an object")
    for token_key in ("input_tokens", "output_tokens"):
        token_value = provider["usage"].get(token_key)
        if isinstance(token_value, bool) or not isinstance(token_value, int) or token_value < 0:
            raise BoundaryError(f"{call_class} provider usage.{token_key} must be a nonnegative integer")
    if isinstance(provider.get("dur_ms"), bool) or not isinstance(provider.get("dur_ms"), int):
        raise BoundaryError(f"{call_class} provider dur_ms must be an integer")
    if not isinstance(provider.get("raw_response"), str) or not isinstance(provider.get("error"), str):
        raise BoundaryError(f"{call_class} provider raw_response/error must be strings")
    for required in ("kind", "system", "user", "schema", "provider", "structured_output"):
        if required not in call:
            raise BoundaryError(f"{call_class} provider receipt missing {required}")


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    metrics = arm.get("execution_metrics")
    if not isinstance(metrics, Mapping):
        raise BoundaryError("successful arm execution metrics are missing")
    for list_key, count_key in (
        ("closed_id_violations", "closed_id_violation_count"),
        ("generation_violations", "generation_violation_count"),
        ("verified_evidence_violations", "verified_evidence_violation_count"),
    ):
        rows = metrics.get(list_key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise BoundaryError(f"execution metric {list_key} must be a string array")
        if metrics.get(count_key) != len(set(rows)):
            raise BoundaryError(f"execution metric {count_key} does not match {list_key}")
    for name in (
        "integrated_total_ms", "planner_provider_ms", "deterministic_planning_ms",
        "verified_rate",
    ):
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise BoundaryError(f"execution metric {name} must be nonnegative")
    sections = list((arm.get("retrieval") or {}).get("sections") or ())
    presented = metrics.get("presented_evidence_count")
    verified = metrics.get("verified_evidence_count")
    for name, value in (("presented_evidence_count", presented), ("verified_evidence_count", verified)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BoundaryError(f"execution metric {name} must be a nonnegative integer")
    if presented != len(sections) or verified > presented:
        raise BoundaryError("execution verified/presented evidence counts are inconsistent")
    expected_rate = round(verified / presented, 6) if presented else 0.0
    if float(metrics["verified_rate"]) != expected_rate:
        raise BoundaryError("execution verified rate is inconsistent")


def _validate_accounting(arms: Mapping[str, Any]) -> None:
    baseline = arms[BASELINE_ARM]
    candidate = arms[CANDIDATE_ARM]
    if baseline.get("baseline_retrieval_shared") is not False:
        raise BoundaryError("baseline arm cannot share its own retrieval")
    for arm_id, arm in ((BASELINE_ARM, baseline), (CANDIDATE_ARM, candidate)):
        accounting = arm.get("accounting")
        if not isinstance(accounting, Mapping):
            raise BoundaryError(f"{arm_id} accounting is missing")
        if accounting.get("baseline_answer_added") is not False:
            raise BoundaryError("candidate inclusive accounting added baseline answer")
        marginal = accounting.get("marginal") or {}
        if marginal.get("usage") != arm.get("usage"):
            raise BoundaryError(f"{arm_id} marginal usage mismatch")
        if marginal.get("wall_ms") != arm.get("wall_ms"):
            raise BoundaryError(f"{arm_id} marginal wall mismatch")

    baseline_accounting = baseline["accounting"]
    if baseline_accounting.get("inclusive") != baseline_accounting.get("marginal"):
        raise BoundaryError("baseline marginal/inclusive accounting must match")
    if baseline_accounting.get("shared_baseline_retrieval_added") is not False:
        raise BoundaryError("baseline accounting cannot add shared retrieval")

    shared = candidate.get("baseline_retrieval_shared")
    if not isinstance(shared, bool):
        raise BoundaryError("candidate baseline_retrieval_shared must be boolean")
    expected_shared_usage = (
        _usage(baseline.get("retrieval_provider_calls") or ()) if shared else _usage([])
    )
    expected_shared_wall = float(baseline.get("retrieval_wall_ms") or 0) if shared else 0.0
    candidate_accounting = candidate["accounting"]
    if candidate_accounting.get("shared_baseline_retrieval_added") is not shared:
        raise BoundaryError("candidate shared retrieval accounting flag mismatch")
    if candidate_accounting.get("shared_baseline_retrieval_usage") != expected_shared_usage:
        raise BoundaryError("candidate shared retrieval usage mismatch")
    if float(candidate_accounting.get("shared_baseline_retrieval_wall_ms") or 0) != expected_shared_wall:
        raise BoundaryError("candidate shared retrieval wall mismatch")
    expected_inclusive = {
        "usage": _usage_add(candidate["usage"], expected_shared_usage),
        "wall_ms": round(float(candidate["wall_ms"]) + expected_shared_wall, 3),
    }
    if candidate_accounting.get("inclusive") != expected_inclusive:
        raise BoundaryError("candidate inclusive accounting mismatch")
    if candidate_accounting.get("criteria_accounting") != "inclusive":
        raise BoundaryError("candidate frozen criteria must use inclusive accounting")


def validate_product_capture(
    value: Mapping[str, Any], *, expected_case: Mapping[str, Any] | None = None,
    require_success: bool = False,
    expected_runtime: Mapping[str, Any] | None = None,
) -> None:
    if value.get("schema_version") != "adr-0114-gold-free-product-capture-v1":
        raise BoundaryError("unexpected product capture schema")
    if value.get("case_id") not in CASE_IDS or value.get("model") != MODEL:
        raise BoundaryError("product capture case/model mismatch")
    if value.get("adr_id") != ADR_ID or value.get("experiment_id") != EXPERIMENT_ID:
        raise BoundaryError("product capture ADR/experiment mismatch")
    if value.get("run_id") != RUN_ID or value.get("complete") is not True:
        raise BoundaryError("product capture run/completeness mismatch")
    if (
        not isinstance(value.get("authority_generation"), str)
        or not value.get("authority_generation")
        or not isinstance(value.get("authority_as_of"), str)
        or not value.get("authority_as_of")
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("corpus_fingerprint") or ""))
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("run_environment_hash") or ""))
    ):
        raise BoundaryError("product capture corpus identity is missing")
    if expected_runtime is not None:
        expected_identity = {
            "authority_generation": expected_runtime.get("authority_generation"),
            "authority_as_of": expected_runtime.get("authority_as_of"),
            "corpus_fingerprint": expected_runtime.get("corpus_fingerprint"),
            "run_environment_hash": expected_runtime.get("run_environment_hash"),
        }
        actual_identity = {key: value.get(key) for key in expected_identity}
        if actual_identity != expected_identity:
            raise BoundaryError("product capture corpus identity mismatch")
    if expected_case is not None:
        expected = {
            "number": int(expected_case["number"]),
            "case_id": str(expected_case["case_id"]),
            "suite": str(expected_case["suite"]),
            "question": str(expected_case["question"]),
        }
        actual = {key: value.get(key) for key in expected}
        if actual != expected:
            raise BoundaryError(f"product capture public-case mismatch: {actual} != {expected}")
    if value.get("gold_visible_to_product") is not False:
        raise BoundaryError("product capture gold visibility violation")
    _forbid_product_gold({key: child for key, child in value.items() if key != "capture_sha256"})
    if value.get("capture_sha256") != _self_hash(value, "capture_sha256"):
        raise BoundaryError("product capture content hash mismatch")
    arms = value.get("arms") or {}
    if set(arms) != set(ARMS):
        raise BoundaryError("both product arms are required")
    for arm_id in ARMS:
        arm = arms[arm_id]
        if arm.get("arm_id") != arm_id:
            raise BoundaryError("product capture arm identity mismatch")
        if arm.get("status") not in {"complete", "error"}:
            raise BoundaryError("product arm status is invalid")
        if arm.get("status") == "complete" and arm.get("error"):
            raise BoundaryError("complete product arm contains an execution error")
        if arm.get("status") == "error" and not arm.get("error"):
            raise BoundaryError("failed product arm is missing its error")
        if require_success and (arm.get("status") != "complete" or arm.get("error")):
            raise BoundaryError(f"sealed product arm failed: {arm_id}: {arm.get('error')}")
        validate_declared_capture(
            arm["retrieval"]["stage_capture"], str(value["case_id"]), arm_id
        )
        calls = list(arm.get("provider_calls") or ())
        retrieval_calls = list(arm.get("retrieval_provider_calls") or ())
        answer_calls = list(arm.get("answer_provider_calls") or ())
        if retrieval_calls + answer_calls != calls:
            raise BoundaryError("retrieval/answer provider call partition mismatch")
        if require_success and not calls:
            raise BoundaryError(f"successful product arm has no provider receipt: {arm_id}")
        for call in calls:
            _validate_provider_call(call, call_class="product")
            if require_success and (call.get("provider") or {}).get("error"):
                raise BoundaryError(f"successful product arm has provider error: {arm_id}")
        if arm.get("usage") != _usage(calls):
            raise BoundaryError("product usage does not match provider receipts")
        if arm.get("status") == "complete":
            if not isinstance((arm.get("answer") or {}).get("answerable"), bool):
                raise BoundaryError("successful product arm answerable flag is missing")
            _validate_execution_metrics(arm)
    _validate_accounting(arms)


def _capture_file(capture_dir: Path, case_id: str) -> Path:
    return capture_dir / f"{case_id}.json"


def build_product_seal(
    public_path: Path, capture_dir: Path, seal_path: Path,
    case_ids: Sequence[str] = CASE_IDS,
    *, runtime_preload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    public = _read_json(public_path)
    _forbid_product_gold(public)
    if [row["case_id"] for row in public.get("cases") or ()] != list(case_ids):
        raise BoundaryError("public fixture case order mismatch")
    public_by_id = {str(row["case_id"]): row for row in public["cases"]}
    receipts = []
    for case_id in case_ids:
        path = _capture_file(capture_dir, case_id)
        capture = _read_json(path)
        validate_product_capture(
            capture, expected_case=public_by_id[case_id], require_success=True,
            expected_runtime=runtime_preload,
        )
        receipts.append({
            "case_id": case_id,
            "number": int(capture["number"]),
            "suite": str(capture["suite"]),
            "question_sha256": hashlib.sha256(
                str(capture["question"]).encode("utf-8")
            ).hexdigest(),
            "model": capture["model"],
            "run_id": capture["run_id"],
            "authority_generation": capture["authority_generation"],
            "authority_as_of": capture["authority_as_of"],
            "corpus_fingerprint": capture["corpus_fingerprint"],
            "run_environment_hash": capture["run_environment_hash"],
            "complete": capture["complete"],
            "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "sha256": _sha256(path),
            "capture_sha256": capture["capture_sha256"],
            "product_calls": sum(
                len(capture["arms"][arm].get("provider_calls") or ()) for arm in ARMS
            ),
        })
    value = {
        "schema_version": "adr-0114-product-capture-seal-v1",
        "adr_id": ADR_ID,
        "run_id": RUN_ID,
        "model": MODEL,
        "gold_visible_to_product": False,
        "public_fixture_path": str(public_path.relative_to(ROOT)) if public_path.is_relative_to(ROOT) else str(public_path),
        "public_fixture_sha256": _sha256(public_path),
        "case_count": len(receipts),
        "case_receipts": receipts,
        "runtime_preload": deepcopy(runtime_preload),
        "sealed_at": _now(),
    }
    _forbid_product_gold(value)
    value["seal_sha256"] = _self_hash(value, "seal_sha256")
    _write_json(seal_path, value)
    return value


def validate_product_seal(
    seal_path: Path, public_path: Path, capture_dir: Path,
    case_ids: Sequence[str] = CASE_IDS,
    *, metadata_only: bool = False,
) -> dict[str, Any]:
    seal = _read_json(seal_path)
    if seal.get("schema_version") != "adr-0114-product-capture-seal-v1":
        raise BoundaryError("product seal schema mismatch")
    if seal.get("seal_sha256") != _self_hash(seal, "seal_sha256"):
        raise BoundaryError("product seal hash mismatch")
    if seal.get("public_fixture_sha256") != _sha256(public_path):
        raise BoundaryError("public fixture changed after product seal")
    preload = seal.get("runtime_preload")
    if preload is not None:
        if (
            not isinstance(preload, Mapping)
            or preload.get("schema_version")
            != "integrated-legal-research-preload-v1"
            or preload.get("status") != "ready"
            or preload.get("provider_calls") != 0
            or not isinstance(preload.get("article_count"), int)
            or preload.get("article_count") < 1
            or isinstance(preload.get("elapsed_ms"), bool)
            or not isinstance(preload.get("elapsed_ms"), (int, float))
            or preload.get("elapsed_ms") < 0
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(preload.get("corpus_fingerprint") or "")
            )
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(preload.get("run_environment_hash") or "")
            )
            or preload.get("lexicon_compile_missing_enabled") is not False
        ):
            raise BoundaryError("runtime preload receipt is invalid")
    receipts = seal.get("case_receipts") or ()
    if [row.get("case_id") for row in receipts] != list(case_ids):
        raise BoundaryError("product seal does not contain all frozen cases")
    public = _read_json(public_path)
    public_by_id = {str(row["case_id"]): row for row in public.get("cases") or ()}
    for receipt in receipts:
        path = _capture_file(capture_dir, str(receipt["case_id"]))
        if receipt.get("sha256") != _sha256(path):
            raise BoundaryError(f"sealed product capture changed: {receipt['case_id']}")
        case_id = str(receipt["case_id"])
        expected_case = public_by_id[case_id]
        if metadata_only:
            expected_receipt = {
                "number": int(expected_case["number"]),
                "suite": str(expected_case["suite"]),
                "question_sha256": hashlib.sha256(
                    str(expected_case["question"]).encode("utf-8")
                ).hexdigest(),
                "model": MODEL,
                "run_id": RUN_ID,
                "complete": True,
            }
            if any(receipt.get(key) != value for key, value in expected_receipt.items()):
                raise BoundaryError(f"product seal metadata mismatch: {case_id}")
            continue
        capture = _read_json(path)
        validate_product_capture(
            capture, expected_case=expected_case, require_success=True,
            expected_runtime=preload,
        )
        expected_receipt = {
            "number": int(capture["number"]),
            "suite": str(capture["suite"]),
            "question_sha256": hashlib.sha256(
                str(capture["question"]).encode("utf-8")
            ).hexdigest(),
            "model": MODEL,
            "run_id": RUN_ID,
            "authority_generation": capture["authority_generation"],
            "authority_as_of": capture["authority_as_of"],
            "corpus_fingerprint": capture["corpus_fingerprint"],
            "run_environment_hash": capture["run_environment_hash"],
            "complete": True,
        }
        if any(receipt.get(key) != value for key, value in expected_receipt.items()):
            raise BoundaryError(f"product seal metadata mismatch: {case_id}")
    return seal


def open_scoring_fixture(
    scoring_path: Path, seal_path: Path, public_path: Path, capture_dir: Path,
    case_ids: Sequence[str] = CASE_IDS,
    *, input_lock: Path = INPUT_LOCK, cm_source: Path = CM_SOURCE,
    metadata_only: bool = False,
    prevalidated_seal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The sole gold-opening function; seal validation must finish first."""
    if prevalidated_seal is None:
        validate_product_seal(
            seal_path, public_path, capture_dir, case_ids,
            metadata_only=metadata_only,
        )
    elif [
        row.get("case_id") for row in prevalidated_seal.get("case_receipts") or ()
    ] != list(case_ids):
        raise BoundaryError("prevalidated product seal case order mismatch")
    fixture = fixture_integrity_receipt(
        input_lock=input_lock, cm_source=cm_source,
        public_path=public_path, scoring_path=scoring_path,
    )
    if not fixture["ready"]:
        raise BoundaryError("canonical public/scoring fixture integrity failed")
    scoring = _read_json(scoring_path)
    if scoring.get("schema_version") != "adr-0114-offline-scoring-fixture-v1":
        raise BoundaryError("offline scoring fixture schema mismatch")
    if [row.get("case_id") for row in scoring.get("cases") or ()] != list(case_ids):
        raise BoundaryError("offline scoring fixture case order mismatch")
    return scoring


def paired_judge_user(
    public_case: Mapping[str, Any], score_case: Mapping[str, Any],
    product_capture: Mapping[str, Any],
) -> str:
    products = {
        arm: {
            "answer": product_capture["arms"][arm]["answer"],
            "evidence": [
                {key: row.get(key) for key in ("rank", "doc_id", "node", "doc", "path")}
                for row in product_capture["arms"][arm]["retrieval"]["sections"]
            ],
        }
        for arm in ARMS
    }
    return (
        f"[질문]\n{public_case['question']}\n\n"
        f"[기준답변 — 채점 전용]\n{score_case['reference_answer']}\n\n"
        f"[정답 좌표 — 검색 실패 진단 전용]\n"
        f"{json.dumps(score_case['gold_articles'], ensure_ascii=False, indent=2)}\n\n"
        f"[봉인된 제품 답변 두 개 — 수정 금지]\n"
        f"{json.dumps(products, ensure_ascii=False, indent=2)}"
    )


def _derived_paired(baseline: bool, candidate: bool) -> str:
    if candidate and not baseline:
        return "candidate_only"
    if baseline and not candidate:
        return "baseline_only"
    if baseline and candidate:
        return "both_correct"
    return "both_wrong"


def execute_judge_case(
    public_case: Mapping[str, Any], score_case: Mapping[str, Any],
    product_capture: Mapping[str, Any], real_llm: Any,
) -> dict[str, Any]:
    """One paired Haiku call; its output is score-only and cannot mutate products."""
    frozen_product_hash = _json_sha256(product_capture)
    recording = RecordingLLM(real_llm)
    user = paired_judge_user(public_case, score_case, product_capture)
    started = time.perf_counter()
    output = recording.structured(
        f"adr0114.judge.{public_case['case_id']}", JUDGE_SYSTEM, user,
        JUDGE_SCHEMA, max_tokens=2200, effort="high", model=MODEL,
    )
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    if _json_sha256(product_capture) != frozen_product_hash:
        raise BoundaryError("offline judge mutated a sealed product capture")
    if len(recording.audit) != 1:
        raise BoundaryError("paired semantic judge must run exactly once per case")
    if not isinstance(output, Mapping):
        output = {
            "baseline": {"correct": False, "unsupported_definitive_conclusion": False, "failure_type": "judge_or_gold_error", "reason": "judge returned no structured output"},
            "candidate": {"correct": False, "unsupported_definitive_conclusion": False, "failure_type": "judge_or_gold_error", "reason": "judge returned no structured output"},
            "paired_outcome": "both_wrong",
            "comparison_reason": "judge failure",
        }
    baseline = bool((output.get("baseline") or {}).get("correct"))
    candidate = bool((output.get("candidate") or {}).get("correct"))
    derived = _derived_paired(baseline, candidate)
    value = {
        "schema_version": "adr-0114-paired-semantic-judge-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "number": int(public_case["number"]),
        "case_id": str(public_case["case_id"]),
        "suite": str(public_case["suite"]),
        "question_sha256": hashlib.sha256(
            str(public_case["question"]).encode("utf-8")
        ).hexdigest(),
        "model": MODEL,
        "class": "offline_evaluator",
        "may_change_product_answer": False,
        "product_capture_sha256": product_capture["capture_sha256"],
        "request": {"system": JUDGE_SYSTEM, "user": user, "schema": JUDGE_SCHEMA},
        "provider_calls": recording.audit,
        "output": _jsonable(output),
        "derived_paired_outcome": derived,
        "provider_declared_paired_outcome": output.get("paired_outcome"),
        "paired_outcome_disagreement": output.get("paired_outcome") != derived,
        "usage": _usage(recording.audit),
        "wall_ms": wall_ms,
        "complete": True,
    }
    value["receipt_sha256"] = _self_hash(value, "receipt_sha256")
    return value


def validate_judge_receipt(
    value: Mapping[str, Any], *, expected_case: Mapping[str, Any],
    product_capture: Mapping[str, Any],
) -> None:
    if value.get("schema_version") != "adr-0114-paired-semantic-judge-v1":
        raise BoundaryError("judge receipt schema mismatch")
    if value.get("receipt_sha256") != _self_hash(value, "receipt_sha256"):
        raise BoundaryError("judge receipt self-hash mismatch")
    expected_identity = {
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "number": int(expected_case["number"]),
        "case_id": str(expected_case["case_id"]),
        "suite": str(expected_case["suite"]),
        "question_sha256": hashlib.sha256(
            str(expected_case["question"]).encode("utf-8")
        ).hexdigest(),
        "complete": True,
    }
    if any(value.get(key) != expected for key, expected in expected_identity.items()):
        raise BoundaryError("judge receipt case/question/run/completeness mismatch")
    if value.get("model") != MODEL or value.get("class") != "offline_evaluator":
        raise BoundaryError("judge model/class mismatch")
    if value.get("may_change_product_answer") is not False:
        raise BoundaryError("judge may not change product answer")
    if value.get("product_capture_sha256") != product_capture.get("capture_sha256"):
        raise BoundaryError("judge does not match current sealed product capture")
    calls = list(value.get("provider_calls") or ())
    if len(calls) != 1:
        raise BoundaryError("paired judge needs exactly one provider receipt")
    _validate_provider_call(calls[0], call_class="offline evaluator")
    if (calls[0].get("provider") or {}).get("error"):
        raise BoundaryError("paired judge provider receipt contains an error")
    if value.get("usage") != _usage(calls):
        raise BoundaryError("judge usage does not match provider receipt")
    output = value.get("output")
    if not isinstance(output, Mapping):
        raise BoundaryError("judge structured output is missing")
    for key in ("baseline", "candidate"):
        grade = output.get(key)
        if not isinstance(grade, Mapping):
            raise BoundaryError(f"judge output missing {key}")
        if grade.get("failure_type") not in ERROR_TYPES:
            raise BoundaryError("judge failure taxonomy value is invalid")
    derived = _derived_paired(
        bool(output["baseline"].get("correct")),
        bool(output["candidate"].get("correct")),
    )
    if value.get("derived_paired_outcome") != derived:
        raise BoundaryError("judge derived paired outcome mismatch")


def _article_root_count(index: Any) -> int:
    return sum(
        node.get("family") == "kr_article" and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items()
    )


def _corpus_fingerprint(index: Any) -> str:
    """Hash the exact scoped search corpus and its deterministic entry data."""

    digest = hashlib.sha256()

    def update(value: Any) -> None:
        digest.update(_json_file_bytes(value))

    update({
        "authority_generation": str(index.authority_generation),
        "authority_as_of": str(index.authority_as_of),
        "scope": sorted(index.scope) if index.scope is not None else None,
        "canonical_doc_ids": sorted(index.canonical_doc_ids or ()),
        "saved_links": index.saved_links,
        "rel_fixes": index.rel_fixes,
    })
    for entry in sorted(
        index.entries,
        key=lambda row: (
            row.doc_id, -1 if row.node is None else int(row.node),
            row.kind, row.key, row.target,
        ),
    ):
        update(asdict(entry))
    for doc_id, view in sorted(index.entry_docs.items()):
        update({
            "doc_id": doc_id,
            "name": view.name,
            "enforce": view.enforce,
            "revised": view.revised,
            "kind": view.kind,
            "folder": view.folder,
            "status": view.status,
            "series": view.series,
            "version": view.version,
            "nodes": view.nodes,
            "blocks": view.blocks,
        })
    return digest.hexdigest()


def _make_llm() -> Any:
    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError(f"configured Haiku provider is unavailable: {llm_mod.MISSING_HINT}")
    real = llm_mod.LLM(model=MODEL)
    if real.model != MODEL:
        raise RuntimeError(f"model policy mismatch: {real.model}")
    if getattr(real, "backend", None) != "anthropic":
        raise RuntimeError(
            f"ADR-0114 Haiku evaluation requires anthropic backend: "
            f"{getattr(real, 'backend', None)}"
        )
    return real


def run_products(
    public: Mapping[str, Any], paths: Mapping[str, Path], *, workers: int, resume: bool
) -> dict[str, Any]:
    if not resume and (paths["seal"].exists() or any(paths["captures"].glob("*.json"))):
        raise BoundaryError("existing product captures require --resume; overwrite is forbidden")
    index = index_mod.current().scoped(None)
    corpus_total = _article_root_count(index)
    preload = integrated_legal_research.preload_resources(index)
    corpus_fingerprint = _corpus_fingerprint(index)
    preload["corpus_fingerprint"] = corpus_fingerprint
    environment = {
        key: value for key, value in preload.items()
        if key not in {"elapsed_ms", "provider_calls", "run_environment_hash"}
    }
    preload["run_environment_hash"] = _json_sha256(environment)
    print(
        "[preload] " + json.dumps(preload, ensure_ascii=False, sort_keys=True),
        flush=True,
    )
    local = threading.local()

    def work(case: Mapping[str, Any]) -> dict[str, Any]:
        if not hasattr(local, "llm"):
            local.llm = _make_llm()
        return execute_product_case(
            index, case, local.llm, corpus_total,
            corpus_fingerprint, preload["run_environment_hash"],
        )

    pending = []
    for case in public["cases"]:
        existing = _capture_file(paths["captures"], case["case_id"])
        if resume and existing.exists():
            validate_product_capture(
                _read_json(existing), expected_case=case, require_success=True,
                expected_runtime=preload,
            )
            continue
        pending.append(case)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, case): case for case in pending}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case = futures[future]
            capture = future.result()
            validate_product_capture(
                capture, expected_case=case, require_success=True
            )
            target = _capture_file(paths["captures"], case["case_id"])
            _write_json(target, capture)
            print(f"[product {position}/{len(pending)}] {case['case_id']}", flush=True)
    return build_product_seal(
        paths["public"], paths["captures"], paths["seal"],
        runtime_preload=preload,
    )


def run_judges(
    public: Mapping[str, Any], scoring: Mapping[str, Any], paths: Mapping[str, Path],
    *, workers: int, resume: bool,
    prevalidated_seal: Mapping[str, Any] | None = None,
) -> None:
    score_by_id = {row["case_id"]: row for row in scoring["cases"]}
    local = threading.local()
    seal = (
        dict(prevalidated_seal)
        if prevalidated_seal is not None
        else validate_product_seal(
            paths["seal"], paths["public"], paths["captures"],
            metadata_only=resume,
        )
    )
    sealed_by_id = {
        str(row["case_id"]): row for row in seal.get("case_receipts") or ()
    }

    if not resume and any(paths["judges"].glob("*.json")):
        raise BoundaryError("existing judge receipts require --resume; overwrite is forbidden")

    def work(case: Mapping[str, Any]) -> dict[str, Any]:
        if not hasattr(local, "llm"):
            local.llm = _make_llm()
        product = _read_json(_capture_file(paths["captures"], case["case_id"]))
        return execute_judge_case(case, score_by_id[case["case_id"]], product, local.llm)

    pending = []
    for case in public["cases"]:
        existing = paths["judges"] / f"{case['case_id']}.json"
        if resume and existing.exists():
            validate_judge_receipt(
                _read_json(existing), expected_case=case,
                product_capture={
                    "capture_sha256": sealed_by_id[case["case_id"]]["capture_sha256"]
                },
            )
            continue
        pending.append(case)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, case): case for case in pending}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case = futures[future]
            receipt = future.result()
            product = _read_json(_capture_file(paths["captures"], case["case_id"]))
            validate_judge_receipt(
                receipt, expected_case=case, product_capture=product,
            )
            _write_json(paths["judges"] / f"{case['case_id']}.json", receipt)
            print(f"[judge {position}/{len(pending)}] {case['case_id']}", flush=True)


def _present_coordinates(capture: Mapping[str, Any]) -> set[tuple[str, int]]:
    final = capture["stages"][-1]
    return set(_rows_to_coordinates(final.get("after") or ()))


def _retrieval_only_arm_grade(
    stage_capture: Mapping[str, Any], expected: Iterable[Mapping[str, Any]],
    companions: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Grade only canonical coordinates in the final product-present stage."""

    stages = list(stage_capture.get("stages") or ())
    if not stages or stages[-1].get("kind") != "present":
        raise BoundaryError("retrieval-only grading requires a final present stage")

    expected_grade = ledger.grade_capture(stage_capture, expected)
    expected_rows = expected_grade["gold_identities"]
    if not expected_rows:
        raise BoundaryError("retrieval-only grading requires expected articles")
    expected_hits = expected_grade["stages"][-1]["gold_after_identities"]

    companion_grade = ledger.grade_capture(stage_capture, companions)
    companion_rows = companion_grade["gold_identities"]
    companion_hits = companion_grade["stages"][-1]["gold_after_identities"]

    presented_rows = stages[-1]["after"]
    expected_keys = {(row["doc_id"], row["node"]) for row in expected_rows}
    expected_hit_keys = {(row["doc_id"], row["node"]) for row in expected_hits}
    companion_keys = {(row["doc_id"], row["node"]) for row in companion_rows}
    companion_hit_keys = {(row["doc_id"], row["node"]) for row in companion_hits}
    presented_keys = {(row["doc_id"], row["node"]) for row in presented_rows}

    def rows(values: set[tuple[str, int]]) -> list[dict[str, Any]]:
        return [
            {"doc_id": doc_id, "node": node}
            for doc_id, node in sorted(values)
        ]

    return {
        "presented_count": len(presented_keys),
        "expected_articles": rows(expected_keys),
        "expected_hits": rows(expected_hit_keys),
        "missing_expected": rows(expected_keys - expected_hit_keys),
        "expected_hit_count": len(expected_hit_keys),
        "expected_total": len(expected_keys),
        "all_expected_present": expected_keys.issubset(presented_keys),
        "required_companions": rows(companion_keys),
        "companion_hits": rows(companion_hit_keys),
        "missing_companions": rows(companion_keys - companion_hit_keys),
        "companion_hit_count": len(companion_hit_keys),
        "companion_total": len(companion_keys),
        "all_companions_present": companion_keys.issubset(presented_keys),
        "additional_presented_count": len(
            presented_keys - expected_keys - companion_keys
        ),
    }


def _retrieval_only_paired(baseline: bool, candidate: bool) -> str:
    if candidate and not baseline:
        return "candidate_only"
    if baseline and not candidate:
        return "baseline_only"
    return "both_pass" if baseline else "both_fail"


def grade_retrieval_only_case(
    product_capture: Mapping[str, Any], score_case: Mapping[str, Any],
) -> dict[str, Any]:
    """Join sealed product output with gold using no semantic judge."""

    if product_capture.get("case_id") != score_case.get("case_id"):
        raise BoundaryError("retrieval-only product/scoring case mismatch")
    expected = list(score_case.get("gold_articles") or ())
    companions = list(score_case.get("required_companions") or ())
    arms = {
        arm: _retrieval_only_arm_grade(
            product_capture["arms"][arm]["retrieval"]["stage_capture"],
            expected,
            companions,
        )
        for arm in ARMS
    }
    return {
        "case_id": str(product_capture["case_id"]),
        "corpus_article_roots": int(product_capture["corpus_article_roots"]),
        "arms": arms,
        "paired_outcome": _retrieval_only_paired(
            bool(arms[BASELINE_ARM]["all_expected_present"]),
            bool(arms[CANDIDATE_ARM]["all_expected_present"]),
        ),
    }


def _summarize_retrieval_only(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    corpus_totals = {int(row["corpus_article_roots"]) for row in rows}
    if len(corpus_totals) != 1:
        raise BoundaryError("retrieval-only captures have inconsistent corpus totals")
    corpus_total = next(iter(corpus_totals))
    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        values = [row["arms"][arm] for row in rows]
        hits = sum(int(value["expected_hit_count"]) for value in values)
        total = sum(int(value["expected_total"]) for value in values)
        companion_hits = sum(int(value["companion_hit_count"]) for value in values)
        companion_total = sum(int(value["companion_total"]) for value in values)
        presented = [int(value["presented_count"]) for value in values]
        by_arm[arm] = {
            "expected_hits": hits,
            "expected_total": total,
            "golden_recall": round(hits / total, 6) if total else None,
            "all_expected_cases": sum(
                bool(value["all_expected_present"]) for value in values
            ),
            "case_total": len(values),
            "companion_hits": companion_hits,
            "companion_total": companion_total,
            "companion_recall": (
                round(companion_hits / companion_total, 6)
                if companion_total else None
            ),
            "all_companion_cases": sum(
                bool(value["all_companions_present"]) for value in values
            ),
            "presented_total": sum(presented),
            "presented_mean": round(statistics.mean(presented), 6) if presented else 0,
            "presented_p50": statistics.median(presented) if presented else 0,
            "presented_p95": _percentile(presented, .95),
            "selectivity": (
                round(statistics.mean(presented) / corpus_total, 10)
                if presented and corpus_total else 0
            ),
        }
    paired = Counter(str(row["paired_outcome"]) for row in rows)
    return {
        "grading_rule": "expected_articles subset_of final_present_coordinates",
        "cases": len(rows),
        "corpus_article_roots": corpus_total,
        "judge_calls": 0,
        "by_arm": by_arm,
        "paired_outcomes": {
            key: int(paired.get(key, 0))
            for key in ("candidate_only", "baseline_only", "both_pass", "both_fail")
        },
    }


def validate_retrieval_only_report(
    value: Mapping[str, Any], *, paths: Mapping[str, Path],
) -> None:
    if value.get("schema_version") != "deterministic-retrieval-only-evaluation-v1":
        raise BoundaryError("retrieval-only report schema mismatch")
    if value.get("adr_id") != ADR_ID or value.get("experiment_id") != EXPERIMENT_ID:
        raise BoundaryError("retrieval-only report experiment mismatch")
    if value.get("run_id") != RUN_ID or value.get("judge_calls") != 0:
        raise BoundaryError("retrieval-only report judge contract mismatch")
    if value.get("product_seal_sha256") != _sha256(paths["seal"]):
        raise BoundaryError("retrieval-only report product seal mismatch")
    if value.get("scoring_fixture_sha256") != _sha256(paths["scoring"]):
        raise BoundaryError("retrieval-only report scoring fixture mismatch")
    if value.get("artifact_sha256") != _self_hash(value, "artifact_sha256"):
        raise BoundaryError("retrieval-only report self-hash mismatch")


def write_retrieval_only_report(
    public: Mapping[str, Any], scoring: Mapping[str, Any],
    paths: Mapping[str, Path], *,
    prevalidated_seal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write an immutable retrieval report after the product seal is valid."""

    target = paths["retrieval_only"]
    if target.exists():
        existing = _read_json(target)
        validate_retrieval_only_report(existing, paths=paths)
        return existing
    seal = (
        dict(prevalidated_seal)
        if prevalidated_seal is not None
        else validate_product_seal(
            paths["seal"], paths["public"], paths["captures"],
            metadata_only=False,
        )
    )
    sealed_ids = [str(row["case_id"]) for row in seal["case_receipts"]]
    public_ids = [str(row["case_id"]) for row in public["cases"]]
    if sealed_ids != public_ids:
        raise BoundaryError("retrieval-only report requires every sealed public case")
    score_by_id = {str(row["case_id"]): row for row in scoring["cases"]}
    rows = []
    for case in public["cases"]:
        case_id = str(case["case_id"])
        product = _read_json(_capture_file(paths["captures"], case_id))
        validate_product_capture(
            product, expected_case=case, require_success=True,
            expected_runtime=seal.get("runtime_preload"),
        )
        rows.append(grade_retrieval_only_case(product, score_by_id[case_id]))
    summary = _summarize_retrieval_only(rows)
    value = {
        "schema_version": "deterministic-retrieval-only-evaluation-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "product_seal_path": (
            str(paths["seal"].relative_to(ROOT))
            if paths["seal"].is_relative_to(ROOT) else str(paths["seal"])
        ),
        "product_seal_sha256": _sha256(paths["seal"]),
        "scoring_fixture_path": (
            str(paths["scoring"].relative_to(ROOT))
            if paths["scoring"].is_relative_to(ROOT) else str(paths["scoring"])
        ),
        "scoring_fixture_sha256": _sha256(paths["scoring"]),
        "gold_opened_after_product_seal": True,
        "judge_calls": 0,
        "judge_model": None,
        "summary": summary,
        "cases": rows,
        "completed_at": _now(),
    }
    value["artifact_sha256"] = _self_hash(value, "artifact_sha256")
    _write_json_once_or_same(target, value)
    return value


def _summarize(rows: Sequence[Mapping[str, Any]], ledger_artifact: Mapping[str, Any]) -> dict[str, Any]:
    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        values = [row["arms"][arm] for row in rows]
        marginal_calls = [
            call for value in values for call in value["product"]["provider_calls"]
        ]
        inclusive_calls: list[Mapping[str, Any]] = []
        for row, value in zip(rows, values):
            inclusive_calls.extend(value["product"]["provider_calls"])
            if (
                arm == CANDIDATE_ARM
                and value["product"].get("baseline_retrieval_shared")
            ):
                inclusive_calls.extend(
                    row["arms"][BASELINE_ARM]["product"]["retrieval_provider_calls"]
                )
        marginal_walls = [float(value["product"]["wall_ms"]) for value in values]
        inclusive_walls = [
            float(value["product"]["accounting"]["inclusive"]["wall_ms"])
            for value in values
        ]
        provider_walls = [
            float((call.get("provider") or {}).get("dur_ms") or 0)
            for call in inclusive_calls
        ]
        presented = [int(value["presented_count"]) for value in values]
        gold_total = sum(int(value["gold_total"]) for value in values)
        gold_hits = sum(int(value["gold_hits"]) for value in values)
        companion_total = sum(int(value["companion_total"]) for value in values)
        companion_hits = sum(int(value["companion_hits"]) for value in values)
        correct = sum(bool(value["judge"]["correct"]) for value in values)
        metrics = [value["product"].get("execution_metrics") or {} for value in values]
        verified_count = sum(int(metric.get("verified_evidence_count") or 0) for metric in metrics)
        verified_denominator = sum(int(metric.get("presented_evidence_count") or 0) for metric in metrics)
        by_arm[arm] = {
            "execution_success": sum(value["product"].get("status") == "complete" for value in values),
            "execution_total": len(values),
            "answer_correct": correct,
            "answer_total": len(values),
            "answer_accuracy": round(correct / len(values), 6) if values else 0,
            "answerable": sum(bool(value["product"]["answer"].get("answerable")) for value in values),
            "decisive_gold_hits": gold_hits,
            "decisive_gold_total": gold_total,
            "decisive_golden_recall": round(gold_hits / gold_total, 6) if gold_total else 0,
            "all_gold_cases": sum(bool(value["all_gold_hit"]) for value in values),
            "required_companion_hits": companion_hits,
            "required_companion_total": companion_total,
            "required_companion_recall": (
                round(companion_hits / companion_total, 6) if companion_total else 0
            ),
            "all_companion_cases": sum(
                bool(value["all_companions_hit"])
                for value in values if value["companion_total"]
            ),
            "presented_total": sum(presented),
            "presented_mean": round(statistics.mean(presented), 6) if presented else 0,
            "presented_p50": statistics.median(presented) if presented else 0,
            "presented_p95": _percentile(presented, .95),
            "presented_max": max(presented) if presented else 0,
            "before_filter_total": sum(
                int(value["product"]["retrieval"]["filter_before_count"])
                for value in values
            ),
            "after_filter_total": sum(
                int(value["product"]["retrieval"]["filter_after_count"])
                for value in values
            ),
            "product_usage_marginal": _usage(marginal_calls),
            "product_usage_inclusive": _usage(inclusive_calls),
            "product_usage": _usage(inclusive_calls),
            "product_call_errors": _usage(inclusive_calls)["errors"],
            "criteria_accounting": "inclusive",
            "product_wall_ms_marginal_p50": _percentile(marginal_walls, .5),
            "product_wall_ms_marginal_p95": _percentile(marginal_walls, .95),
            "product_wall_ms_inclusive_p50": _percentile(inclusive_walls, .5),
            "product_wall_ms_inclusive_p95": _percentile(inclusive_walls, .95),
            "product_wall_ms_p50": _percentile(inclusive_walls, .5),
            "product_wall_ms_p95": _percentile(inclusive_walls, .95),
            "provider_call_ms_p50": _percentile(provider_walls, .5),
            "provider_call_ms_p95": _percentile(provider_walls, .95),
            "deterministic_planning_ms_p50": _percentile(
                (metric.get("deterministic_planning_ms") or 0 for metric in metrics), .5
            ),
            "deterministic_planning_ms_p95": _percentile(
                (metric.get("deterministic_planning_ms") or 0 for metric in metrics), .95
            ),
            "closed_id_violations": sum(
                int(metric.get("closed_id_violation_count") or 0) for metric in metrics
            ),
            "generation_violations": sum(
                int(metric.get("generation_violation_count") or 0) for metric in metrics
            ),
            "verified_evidence_violations": sum(
                int(metric.get("verified_evidence_violation_count") or 0) for metric in metrics
            ),
            "runtime_errors": sum(
                int(metric.get("runtime_error_count") or 0) for metric in metrics
            ),
            "verified_evidence_count": verified_count,
            "verified_evidence_denominator": verified_denominator,
            "verified_rate": (
                round(verified_count / verified_denominator, 6)
                if verified_denominator else 0.0
            ),
            "unsupported_definitive_conclusions": sum(
                bool(value["judge"].get("unsupported_definitive_conclusion")) for value in values
            ),
        }
    paired = {key: sum(row["paired_outcome"] == key for row in rows) for key in (
        "candidate_only", "baseline_only", "both_correct", "both_wrong"
    )}
    companion_paired = {
        "candidate_only": 0,
        "baseline_only": 0,
        "both_hit": 0,
        "both_miss": 0,
    }
    for row in rows:
        baseline_results = {
            (item["doc_id"], int(item["node"])): bool(item["hit"])
            for item in row["arms"][BASELINE_ARM]["companion_results"]
        }
        candidate_results = {
            (item["doc_id"], int(item["node"])): bool(item["hit"])
            for item in row["arms"][CANDIDATE_ARM]["companion_results"]
        }
        for coordinate in sorted(set(baseline_results) | set(candidate_results)):
            baseline_hit = baseline_results.get(coordinate, False)
            candidate_hit = candidate_results.get(coordinate, False)
            key = (
                "candidate_only" if candidate_hit and not baseline_hit
                else "baseline_only" if baseline_hit and not candidate_hit
                else "both_hit" if baseline_hit and candidate_hit
                else "both_miss"
            )
            companion_paired[key] += 1
    decisive_paired = {
        "candidate_only": 0,
        "baseline_only": 0,
        "both_hit": 0,
        "both_miss": 0,
    }
    for row in rows:
        baseline_results = {
            (item["doc_id"], int(item["node"])): bool(item["hit"])
            for item in row["arms"][BASELINE_ARM]["gold_results"]
        }
        candidate_results = {
            (item["doc_id"], int(item["node"])): bool(item["hit"])
            for item in row["arms"][CANDIDATE_ARM]["gold_results"]
        }
        for coordinate in sorted(set(baseline_results) | set(candidate_results)):
            baseline_hit = baseline_results.get(coordinate, False)
            candidate_hit = candidate_results.get(coordinate, False)
            key = (
                "candidate_only" if candidate_hit and not baseline_hit
                else "baseline_only" if baseline_hit and not candidate_hit
                else "both_hit" if baseline_hit and candidate_hit
                else "both_miss"
            )
            decisive_paired[key] += 1
    judge_calls = [call for row in rows for call in row["judge_receipt"]["provider_calls"]]
    taxonomy: dict[str, int] = {}
    for row in rows:
        for arm in ARMS:
            name = str(row["arms"][arm]["judge"].get("failure_type") or "other")
            if name != "none":
                taxonomy[name] = taxonomy.get(name, 0) + 1
    corpus_total = int(rows[0]["corpus_article_roots"]) if rows else 0
    for arm in ARMS:
        by_arm[arm]["selectivity"] = (
            round(by_arm[arm]["presented_mean"] / corpus_total, 10) if corpus_total else 0
        )
    baseline_usage = by_arm[BASELINE_ARM]["product_usage_inclusive"]
    candidate_usage = by_arm[CANDIDATE_ARM]["product_usage_inclusive"]
    candidate_token_limit = (
        candidate_usage["input_tokens"] <= baseline_usage["input_tokens"] * 1.75
        or candidate_usage["input_tokens"] - baseline_usage["input_tokens"] <= 400_000
    )
    criteria = {
        "candidate_cost_basis": "inclusive: candidate marginal plus shared baseline retrieval only; baseline answer excluded",
        "decisive_hits_noninferior": (
            by_arm[CANDIDATE_ARM]["decisive_gold_hits"]
            >= by_arm[BASELINE_ARM]["decisive_gold_hits"]
        ),
        "decisive_candidate_only_at_least_one": decisive_paired["candidate_only"] >= 1,
        "decisive_baseline_only_zero": decisive_paired["baseline_only"] == 0,
        "all_gold_cases_noninferior": (
            by_arm[CANDIDATE_ARM]["all_gold_cases"]
            >= by_arm[BASELINE_ARM]["all_gold_cases"]
        ),
        "answer_correct_noninferior": (
            by_arm[CANDIDATE_ARM]["answer_correct"]
            >= by_arm[BASELINE_ARM]["answer_correct"]
        ),
        "answer_baseline_only_at_most_one": paired["baseline_only"] <= 1,
        "candidate_unsupported_definitive_zero": (
            by_arm[CANDIDATE_ARM]["unsupported_definitive_conclusions"] == 0
        ),
        "candidate_closed_id_violations_zero": (
            by_arm[CANDIDATE_ARM]["closed_id_violations"] == 0
        ),
        "candidate_generation_violations_zero": (
            by_arm[CANDIDATE_ARM]["generation_violations"] == 0
        ),
        "candidate_verified_evidence_violations_zero": (
            by_arm[CANDIDATE_ARM]["verified_evidence_violations"] == 0
        ),
        "candidate_execution_errors_zero": (
            by_arm[CANDIDATE_ARM]["execution_success"] == len(rows)
            and by_arm[CANDIDATE_ARM]["product_call_errors"] == 0
            and by_arm[CANDIDATE_ARM]["runtime_errors"] == 0
        ),
        "candidate_presented_max_within_32": (
            by_arm[CANDIDATE_ARM]["presented_max"] <= 32
        ),
        "candidate_presented_mean_within_28": (
            by_arm[CANDIDATE_ARM]["presented_mean"] <= 28
        ),
        "candidate_input_token_limit_met": candidate_token_limit,
        "candidate_provider_p95_within_20000_ms": (
            by_arm[CANDIDATE_ARM]["provider_call_ms_p95"] <= 20_000
        ),
        "candidate_deterministic_planning_p95_within_500_ms": (
            by_arm[CANDIDATE_ARM]["deterministic_planning_ms_p95"] <= 500
        ),
        "required_companion_noninferior": (
            by_arm[CANDIDATE_ARM]["required_companion_hits"]
            >= by_arm[BASELINE_ARM]["required_companion_hits"]
            and companion_paired["baseline_only"] == 0
        ),
    }
    criteria["all_frozen_criteria_met"] = all(
        value for key, value in criteria.items() if key != "candidate_cost_basis"
    )
    return {
        "cases": len(rows),
        "corpus_article_roots": corpus_total,
        "by_arm": by_arm,
        "paired_outcomes": paired,
        "paired_delta": by_arm[CANDIDATE_ARM]["answer_correct"] - by_arm[BASELINE_ARM]["answer_correct"],
        "decisive_coordinate_paired": decisive_paired,
        "required_companion_paired": companion_paired,
        "judge_usage": _usage(judge_calls),
        "judge_p50_ms": _percentile((row["judge_receipt"]["wall_ms"] for row in rows), .5),
        "judge_p95_ms": _percentile((row["judge_receipt"]["wall_ms"] for row in rows), .95),
        "judge_paired_label_disagreements": sum(
            bool(row["judge_receipt"].get("paired_outcome_disagreement")) for row in rows
        ),
        "error_taxonomy": dict(sorted(taxonomy.items())),
        "frozen_criteria_measurement": criteria,
        "retrieval_stage_ledger_sha256": ledger_artifact.get("artifact_sha256"),
    }


def _question_markdown(row: Mapping[str, Any], score: Mapping[str, Any], ledger_path: str) -> str:
    blocks = []
    for arm in ARMS:
        product = row["arms"][arm]["product"]
        blocks.append(
            f"### `{arm}`\n\n`````json\n"
            + json.dumps({
                "retrieval": product["retrieval"],
                "answer": product["answer"],
                "provider_calls": product["provider_calls"],
                "usage": product["usage"],
                "accounting": product["accounting"],
                "execution_metrics": product["execution_metrics"],
                "wall_ms": product["wall_ms"],
            }, ensure_ascii=False, indent=2)
            + "\n`````"
        )
    decisions = "\n".join(
        f"| `{arm}` | {row['arms'][arm]['judge']['correct']} | "
        f"`{row['arms'][arm]['judge']['failure_type']}` | "
        f"{row['arms'][arm]['judge']['reason']} |"
        for arm in ARMS
    )
    return f"""# 질문 {int(row['number']):03d} — {row['case_id']}

## 1. 실행 메타

- ADR / experiment / run: `{ADR_ID}` / `{EXPERIMENT_ID}` / `{RUN_ID}`
- 제품·중간·오프라인 judge 모델: `{MODEL}`
- product capture 상태: `sealed exact`
- judge 반복: `paired 1회`
- gold visible to product: `false`

## 2. 사용자 질문 원문

`````text
{row['question']}
`````

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

제품 두 arm의 전체 capture와 provider raw receipt가 봉인된 뒤에만 이 절을 열었다.

`````text
{score['reference_answer']}
`````

`````json
{json.dumps(score['gold_articles'], ensure_ascii=False, indent=2)}
`````

### Required companions — 채점 전용

`````json
{json.dumps(score.get('required_companions') or [], ensure_ascii=False, indent=2)}
`````

## 4. 제품 입력을 구성한 원값

- sealed product capture: `{row['product_capture_path']}`
- product capture SHA-256: `{row['product_capture_sha256']}`

### 회수·탈락 단계 원장 — run·arm별

- 전수 stage ledger: `{ledger_path}`
- 두 arm의 exact coordinate snapshot은 아래 product capture의 `stage_capture`에 전부 보존했다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

{chr(10).join(blocks)}

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

retrieval 내부 router/compiler/verifier 호출은 arm별 `provider_calls`에 호출 순서대로 포함했다.
candidate가 baseline retrieval을 공유했는지는 `baseline_retrieval_shared`에 기록했다.

## 7. 채점 호출과 반복 판정

단일 paired Haiku가 제품 출력을 수정하지 않고 1회 판정했다.

`````json
{json.dumps(row['judge_receipt'], ensure_ascii=False, indent=2)}
`````

## 8. 사례 최종 판정

| arm | 정답 | 실패 유형 | 이유 |
|---|---:|---|---|
{decisions}

- paired outcome: `{row['paired_outcome']}`
- decisive exact hit: baseline `{row['arms'][BASELINE_ARM]['gold_hits']}/{row['arms'][BASELINE_ARM]['gold_total']}`, candidate `{row['arms'][CANDIDATE_ARM]['gold_hits']}/{row['arms'][CANDIDATE_ARM]['gold_total']}`
- required companion exact hit: baseline `{row['arms'][BASELINE_ARM]['companion_hits']}/{row['arms'][BASELINE_ARM]['companion_total']}`, candidate `{row['arms'][CANDIDATE_ARM]['companion_hits']}/{row['arms'][CANDIDATE_ARM]['companion_total']}`
"""


def _artifact_entry(path: Path, description: str, raw: bool = False) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "description": description,
        "contains_raw_prompts_and_outputs": raw,
    }


def _failed_attempt_entries(adr: Path) -> list[dict[str, Any]]:
    """Discover and verify every append-only pre-seal failure receipt."""

    root = (adr / "artifacts" / "failed-attempts").resolve()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for receipt_path in sorted(root.glob("*/receipt.json")):
        receipt = _read_json(receipt_path)
        attempt_dir = receipt_path.parent.resolve()
        expected = {
            "schema_version": "adr-0114-aborted-attempt-v1",
            "adr_id": ADR_ID,
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "attempt_id": attempt_dir.name,
            "status": "aborted_before_product_seal",
            "gold_opened": False,
            "scoring_fixture_opened": False,
            "judge_calls": 0,
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise BoundaryError(f"invalid failed-attempt receipt: {receipt_path}")
        out.append(_artifact_entry(
            receipt_path,
            "aborted pre-seal attempt receipt; gold was not opened",
        ))
        partial = list(receipt.get("partial_captures") or ())
        if not partial:
            raise BoundaryError(f"failed-attempt receipt has no partial captures: {receipt_path}")
        seen_cases: set[str] = set()
        for row in partial:
            case_id = str(row.get("case_id") or "")
            relative = Path(str(row.get("path") or ""))
            if (
                case_id not in CASE_IDS or case_id in seen_cases
                or relative.is_absolute() or not str(relative)
            ):
                raise BoundaryError(f"invalid failed-attempt capture row: {receipt_path}")
            seen_cases.add(case_id)
            target = (attempt_dir / relative).resolve()
            if not target.is_relative_to(attempt_dir) or not target.is_file():
                raise BoundaryError(f"failed-attempt capture escaped or is missing: {target}")
            if row.get("sha256") != _sha256(target):
                raise BoundaryError(f"failed-attempt capture hash mismatch: {target}")
            out.append(_artifact_entry(
                target,
                f"partial product capture from aborted pre-seal attempt {case_id}",
                True,
            ))
    return out


def _validated_existing_artifact_entries(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Keep prior concrete artifacts only when their current bytes still match."""

    out: list[dict[str, Any]] = []
    for row in value.get("files") or ():
        path_value = str(row.get("path") or "")
        if not path_value or path_value == "TODO" or row.get("sha256") == "PENDING":
            continue
        path = Path(path_value)
        target = path if path.is_absolute() else ROOT / path
        if not target.is_file():
            raise BoundaryError(f"previously manifested artifact is missing: {target}")
        if row.get("sha256") != _sha256(target) or row.get("bytes") != target.stat().st_size:
            raise BoundaryError(f"previously manifested artifact changed: {target}")
        out.append(deepcopy(dict(row)))
    return out


def _merge_artifact_entries(*groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Path-keyed, deterministic, append-only artifact manifest merge."""

    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            row = deepcopy(dict(raw))
            path = str(row.get("path") or "")
            if not path:
                raise BoundaryError("artifact row has no path")
            previous = merged.get(path)
            if previous is not None:
                identity = ("sha256", "bytes", "contains_raw_prompts_and_outputs")
                if any(previous.get(key) != row.get(key) for key in identity):
                    raise BoundaryError(f"append-only artifact conflict: {path}")
                continue
            merged[path] = row
    return [merged[path] for path in sorted(merged)]


def _summary_provider_call(call: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the frozen accounting fields; raw I/O stays in its receipt."""

    provider = call.get("provider") or {}
    return {
        "provider": {
            "usage": deepcopy(provider.get("usage") or {}),
            "dur_ms": provider.get("dur_ms", 0),
            "error": str(provider.get("error") or ""),
        }
    }


def _summary_product_arm(arm: Mapping[str, Any]) -> dict[str, Any]:
    """Bound finalizer memory without weakening any measured criterion."""

    stage_capture = (arm.get("retrieval") or {}).get("stage_capture") or {}
    filter_stages = [
        stage for stage in stage_capture.get("stages") or ()
        if stage.get("kind") == "filter"
    ]
    if len(filter_stages) != 1:
        raise BoundaryError("product arm must contain exactly one filter stage")
    filter_stage = filter_stages[0]
    return {
        "status": arm.get("status"),
        "baseline_retrieval_shared": arm.get("baseline_retrieval_shared"),
        "retrieval": {
            "stage_capture_sha256": stage_capture.get("capture_sha256"),
            "filter_before_count": int(filter_stage["before_count"]),
            "filter_after_count": int(filter_stage["after_count"]),
        },
        "answer": {"answerable": bool((arm.get("answer") or {}).get("answerable"))},
        "execution_metrics": deepcopy(arm.get("execution_metrics") or {}),
        "provider_calls": [
            _summary_provider_call(call) for call in arm.get("provider_calls") or ()
        ],
        "retrieval_provider_calls": [
            _summary_provider_call(call)
            for call in arm.get("retrieval_provider_calls") or ()
        ],
        "accounting": deepcopy(arm.get("accounting") or {}),
        "wall_ms": float(arm.get("wall_ms") or 0),
    }


def _summary_judge_receipt(judge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider_calls": [
            _summary_provider_call(call) for call in judge.get("provider_calls") or ()
        ],
        "wall_ms": float(judge.get("wall_ms") or 0),
        "paired_outcome_disagreement": bool(
            judge.get("paired_outcome_disagreement")
        ),
    }


def _finalize_shard_file(paths: Mapping[str, Path], case_id: str) -> Path:
    if case_id not in CASE_IDS:
        raise BoundaryError(f"unknown finalize shard case: {case_id}")
    return paths["finalize_shards"] / f"{case_id}.json"


def _finalize_seal_receipts(
    seal: Mapping[str, Any], paths: Mapping[str, Path]
) -> dict[str, Mapping[str, Any]]:
    """Validate the immutable seal document without rereading all 61 captures."""

    if seal.get("schema_version") != "adr-0114-product-capture-seal-v1":
        raise BoundaryError("product seal schema mismatch during finalize")
    if seal.get("seal_sha256") != _self_hash(seal, "seal_sha256"):
        raise BoundaryError("product seal content hash mismatch during finalize")
    if (
        seal.get("adr_id") != ADR_ID
        or seal.get("run_id") != RUN_ID
        or seal.get("model") != MODEL
        or seal.get("gold_visible_to_product") is not False
        or seal.get("case_count") != len(CASE_IDS)
        or seal.get("public_fixture_sha256") != _sha256(paths["public"])
    ):
        raise BoundaryError("product seal identity mismatch during finalize")
    preload = seal.get("runtime_preload")
    if (
        not isinstance(preload, Mapping)
        or preload.get("schema_version")
        != "integrated-legal-research-preload-v1"
        or preload.get("status") != "ready"
        or preload.get("provider_calls") != 0
        or preload.get("lexicon_compile_missing_enabled") is not False
    ):
        raise BoundaryError("product seal runtime receipt is invalid during finalize")
    receipts = list(seal.get("case_receipts") or ())
    if [row.get("case_id") for row in receipts] != list(CASE_IDS):
        raise BoundaryError("product seal case order mismatch during finalize")
    return {str(row["case_id"]): row for row in receipts}


def _expected_question_target(
    adr: Path, question_entry: Mapping[str, Any]
) -> Path:
    root = (adr / "실험").resolve()
    target = (root / str(question_entry.get("file") or "")).resolve()
    if not target.is_relative_to(root):
        raise BoundaryError(f"question artifact escaped ADR experiment dir: {target}")
    return target


def _validate_finalize_shard(
    value: Mapping[str, Any], *, expected_case: Mapping[str, Any],
    expected_question: Mapping[str, Any], seal: Mapping[str, Any],
    paths: Mapping[str, Path], adr: Path,
) -> None:
    expected_fields = {
        "schema_version", "adr_id", "experiment_id", "run_id", "case_id",
        "number", "suite", "product_seal_sha256",
        "product_capture_sha256", "product_capture_content_sha256",
        "judge_receipt_sha256", "question_path", "question_sha256", "row",
        "graded_ledgers", "graded_ledger_sha256", "artifact_sha256",
    }
    if set(value) != expected_fields:
        raise BoundaryError("finalize shard fields differ")
    case_id = str(expected_case["case_id"])
    identity = {
        "schema_version": "adr-0114-finalize-shard-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "case_id": case_id,
        "number": int(expected_case["number"]),
        "suite": str(expected_case["suite"]),
    }
    if any(value.get(key) != expected for key, expected in identity.items()):
        raise BoundaryError(f"finalize shard identity mismatch: {case_id}")
    if value.get("artifact_sha256") != _self_hash(value, "artifact_sha256"):
        raise BoundaryError(f"finalize shard content hash mismatch: {case_id}")
    receipts = _finalize_seal_receipts(seal, paths)
    sealed = receipts[case_id]
    if (
        value.get("product_seal_sha256") != _sha256(paths["seal"])
        or value.get("product_capture_sha256") != sealed.get("sha256")
        or value.get("product_capture_content_sha256")
        != sealed.get("capture_sha256")
    ):
        raise BoundaryError(f"finalize shard product lineage mismatch: {case_id}")
    judge_path = paths["judges"] / f"{case_id}.json"
    if value.get("judge_receipt_sha256") != _sha256(judge_path):
        raise BoundaryError(f"finalize shard judge lineage mismatch: {case_id}")
    question_path = _expected_question_target(adr, expected_question)
    expected_relative = (
        str(question_path.relative_to(ROOT))
        if question_path.is_relative_to(ROOT) else str(question_path)
    )
    if (
        value.get("question_path") != expected_relative
        or value.get("question_sha256") != _sha256(question_path)
        or not _completed_question_result(question_path, case_id)
    ):
        raise BoundaryError(f"finalize shard question lineage mismatch: {case_id}")
    row = value.get("row")
    if not isinstance(row, Mapping):
        raise BoundaryError(f"finalize shard row is missing: {case_id}")
    if (
        row.get("case_id") != case_id
        or row.get("number") != int(expected_case["number"])
        or row.get("suite") != str(expected_case["suite"])
        or row.get("question") != str(expected_case["question"])
        or row.get("product_capture_sha256")
        != value.get("product_capture_sha256")
        or row.get("judge_receipt_sha256")
        != value.get("judge_receipt_sha256")
        or set(row.get("arms") or {}) != set(ARMS)
    ):
        raise BoundaryError(f"finalize shard compact row mismatch: {case_id}")
    graded = list(value.get("graded_ledgers") or ())
    if len(graded) != len(ARMS):
        raise BoundaryError(f"finalize shard must contain both graded ledgers: {case_id}")
    by_arm: dict[str, Mapping[str, Any]] = {}
    for item in graded:
        arm_id = str(item.get("arm_id") or "")
        if arm_id in by_arm or arm_id not in ARMS or item.get("case_id") != case_id:
            raise BoundaryError(f"finalize shard graded ledger identity mismatch: {case_id}")
        ledger.validate_graded_ledger(
            item,
            expected_stage_ids=[row["stage_id"] for row in STAGE_PLAN[arm_id]],
        )
        by_arm[arm_id] = item
    hashes = value.get("graded_ledger_sha256") or {}
    if (
        set(hashes) != set(ARMS)
        or any(hashes[arm] != by_arm[arm].get("ledger_sha256") for arm in ARMS)
    ):
        raise BoundaryError(f"finalize shard graded ledger hash mismatch: {case_id}")


def materialize_finalize_shard(
    case_id: str, *, adr: Path = ADR,
    paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Materialize one case in an isolated process and release its raw arena."""

    paths = dict(paths or _artifact_paths(adr))
    public = _read_json(paths["public"])
    _forbid_product_gold(public)
    scoring = _read_json(paths["scoring"])
    manifest = _read_json(adr / "실험/manifest.json")
    public_cases = list(public.get("cases") or ())
    scoring_cases = list(scoring.get("cases") or ())
    question_entries = list(manifest.get("questions") or ())
    if (
        [row.get("case_id") for row in public_cases] != list(CASE_IDS)
        or [row.get("case_id") for row in scoring_cases] != list(CASE_IDS)
        or [row.get("case_id") for row in question_entries] != list(CASE_IDS)
    ):
        raise BoundaryError("finalize shard fixture/manifest case order mismatch")
    case = next(row for row in public_cases if row["case_id"] == case_id)
    score = next(row for row in scoring_cases if row["case_id"] == case_id)
    question_entry = next(
        row for row in question_entries if row["case_id"] == case_id
    )
    seal = _read_json(paths["seal"])
    sealed = _finalize_seal_receipts(seal, paths)[case_id]
    product_path = _capture_file(paths["captures"], case_id)
    if sealed.get("sha256") != _sha256(product_path):
        raise BoundaryError(f"sealed product bytes changed: {case_id}")
    product = _read_json(product_path)
    validate_product_capture(
        product, expected_case=case, require_success=True,
        expected_runtime=seal.get("runtime_preload"),
    )
    if product.get("capture_sha256") != sealed.get("capture_sha256"):
        raise BoundaryError(f"sealed product content identity changed: {case_id}")
    judge_path = paths["judges"] / f"{case_id}.json"
    judge = _read_json(judge_path)
    validate_judge_receipt(judge, expected_case=case, product_capture=product)
    gold = [
        (str(row["doc_id"]), int(row["node"]))
        for row in score["gold_articles"]
    ]
    companions = [
        (str(row["doc_id"]), int(row["node"]))
        for row in score.get("required_companions") or ()
    ]
    arm_rows: dict[str, Any] = {}
    graded_ledgers: list[dict[str, Any]] = []
    for arm, judge_key in (
        (BASELINE_ARM, "baseline"), (CANDIDATE_ARM, "candidate")
    ):
        stage_capture = product["arms"][arm]["retrieval"]["stage_capture"]
        graded = ledger.grade_capture(stage_capture, gold)
        graded_ledgers.append(graded)
        present = _present_coordinates(stage_capture)
        arm_rows[arm] = {
            "product": product["arms"][arm],
            "presented_count": len(present),
            "gold_hits": len(present & set(gold)),
            "gold_total": len(gold),
            "all_gold_hit": set(gold).issubset(present),
            "companion_hits": len(present & set(companions)),
            "companion_total": len(companions),
            "all_companions_hit": set(companions).issubset(present),
            "gold_results": [
                {
                    **row,
                    "hit": (row["doc_id"], int(row["node"])) in present,
                }
                for row in score["gold_articles"]
            ],
            "companion_results": [
                {
                    **row,
                    "hit": (row["doc_id"], int(row["node"])) in present,
                }
                for row in score.get("required_companions") or ()
            ],
            "judge": deepcopy(judge["output"][judge_key]),
        }
    full_row = {
        "number": int(case["number"]),
        "case_id": case_id,
        "suite": str(case["suite"]),
        "question": str(case["question"]),
        "corpus_article_roots": int(product["corpus_article_roots"]),
        "product_capture_path": str(product_path.relative_to(ROOT)),
        "product_capture_sha256": _sha256(product_path),
        "judge_receipt_path": str(judge_path.relative_to(ROOT)),
        "judge_receipt_sha256": _sha256(judge_path),
        "judge_receipt": judge,
        "paired_outcome": judge["derived_paired_outcome"],
        "arms": arm_rows,
    }
    question_path = _expected_question_target(adr, question_entry)
    if not _completed_question_result(question_path, case_id):
        _write_question_result(
            question_path,
            _question_markdown(
                full_row, score, str(paths["ledger"].relative_to(ROOT))
            ),
        )
    for arm in ARMS:
        arm_rows[arm]["product"] = _summary_product_arm(product["arms"][arm])
    full_row["judge_receipt"] = _summary_judge_receipt(judge)
    shard = {
        "schema_version": "adr-0114-finalize-shard-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "case_id": case_id,
        "number": int(case["number"]),
        "suite": str(case["suite"]),
        "product_seal_sha256": _sha256(paths["seal"]),
        "product_capture_sha256": full_row["product_capture_sha256"],
        "product_capture_content_sha256": product["capture_sha256"],
        "judge_receipt_sha256": full_row["judge_receipt_sha256"],
        "question_path": (
            str(question_path.relative_to(ROOT))
            if question_path.is_relative_to(ROOT) else str(question_path)
        ),
        "question_sha256": _sha256(question_path),
        "row": full_row,
        "graded_ledgers": graded_ledgers,
        "graded_ledger_sha256": {
            item["arm_id"]: item["ledger_sha256"] for item in graded_ledgers
        },
    }
    shard["artifact_sha256"] = _self_hash(shard, "artifact_sha256")
    _validate_finalize_shard(
        shard, expected_case=case, expected_question=question_entry,
        seal=seal, paths=paths, adr=adr,
    )
    _write_json_once_or_same(_finalize_shard_file(paths, case_id), shard)
    return {
        "case_id": case_id,
        "path": str(_finalize_shard_file(paths, case_id)),
        "artifact_sha256": shard["artifact_sha256"],
    }


def _ensure_finalize_shards(
    public: Mapping[str, Any], paths: Mapping[str, Path], *, adr: Path,
    input_lock: Path, cm_source: Path,
) -> list[Path]:
    """Create missing shards sequentially; each raw capture dies with its child."""

    out: list[Path] = []
    script = Path(__file__).resolve()
    for position, case in enumerate(public.get("cases") or (), 1):
        case_id = str(case["case_id"])
        target = _finalize_shard_file(paths, case_id)
        if not target.exists():
            environment = dict(os.environ)
            environment["RAG_LEXICON_COMPILE_MISSING"] = "0"
            command = [
                sys.executable, str(script), "--finalize-case", case_id,
                "--adr", str(adr), "--input-lock", str(input_lock),
                "--cm-source", str(cm_source),
            ]
            completed = subprocess.run(
                command, cwd=str(ROOT), env=environment, text=True,
                capture_output=True, check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                raise BoundaryError(
                    f"finalize shard child failed for {case_id}: "
                    f"{detail[-4000:]}"
                )
        if not target.is_file():
            raise BoundaryError(f"finalize shard was not materialized: {case_id}")
        out.append(target)
        print(f"[finalize-shard {position}/{len(CASE_IDS)}] {case_id}", flush=True)
    return out


def _existing_ledger_case_hashes(
    artifact: Mapping[str, Any]
) -> dict[tuple[str, str], str]:
    ledger.validate_experiment_artifact(artifact)
    if (
        artifact.get("adr_id") != ADR_ID
        or artifact.get("experiment_id") != EXPERIMENT_ID
        or [run.get("run_id") for run in artifact.get("runs") or ()] != [RUN_ID]
    ):
        raise BoundaryError("existing retrieval ledger identity mismatch")
    out: dict[tuple[str, str], str] = {}
    run = artifact["runs"][0]
    for arm in run["arms"]:
        arm_id = str(arm["arm_id"])
        for case in arm["cases"]:
            out[(str(case["case_id"]), arm_id)] = str(case["ledger_sha256"])
    expected = {(case_id, arm) for case_id in CASE_IDS for arm in ARMS}
    if set(out) != expected:
        raise BoundaryError("existing retrieval ledger case coverage mismatch")
    return out


def _archive_hardlink_once(
    source: Path, archive: Path, *, expected_sha256: str
) -> None:
    """Preserve pre-repair bytes without duplicating multi-gigabyte raw files."""

    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        if _sha256(source) != expected_sha256:
            raise BoundaryError(f"source changed before recovery archive: {source}")
        os.link(source, archive)
    if _sha256(archive) != expected_sha256:
        raise BoundaryError(f"recovery archive hash mismatch: {archive}")


def _rewrite_standard_question_headings(source: Path, target: Path) -> None:
    """Stream the five exact ADR-v4 heading repairs and preserve all payloads."""

    replacements = {
        "## 5. 제품 모델 호출 — system/user/schema/provider raw/structured/usage":
            "## 5. 제품 모델 호출 — run·arm별 실제 원문",
        "## 6. 중간 LLM 호출":
            "## 6. 중간 LLM 호출 — router/compiler/verifier/repair",
        "## 7. 채점 호출 — 단일 paired Haiku, 제품 수정 금지":
            "## 7. 채점 호출과 반복 판정",
    }
    counts = {key: 0 for key in replacements}
    section_four = "## 4. 제품 입력 원값과 회수·탈락 단계 원장"
    section_four_count = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(
        f".{target.name}.heading-repair-{os.getpid()}-{threading.get_ident()}"
    )
    try:
        with source.open("r", encoding="utf-8", newline="") as reader, \
                temporary.open("w", encoding="utf-8", newline="\n") as writer:
            for raw_line in reader:
                line = raw_line.rstrip("\r\n")
                if line == section_four:
                    section_four_count += 1
                    writer.write("## 4. 제품 입력을 구성한 원값\n\n")
                    writer.write("### 회수·탈락 단계 원장 — run·arm별\n")
                    continue
                replacement = replacements.get(line)
                if replacement is not None:
                    counts[line] += 1
                    writer.write(replacement + "\n")
                else:
                    writer.write(line + "\n")
            writer.flush()
            os.fsync(writer.fileno())
            _drop_file_cache(writer)
            _drop_file_cache(reader)
        if section_four_count != 1 or any(value != 1 for value in counts.values()):
            raise BoundaryError(
                f"question heading repair source contract mismatch: {source}: "
                f"section4={section_four_count}, replacements={counts}"
            )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def repair_question_heading_artifacts(
    *, adr: Path = ADR, paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Recover the finalized raw receipts after ADR-v4 heading validation failed."""

    paths = dict(paths or _artifact_paths(adr))
    recovery_root = (
        adr / "artifacts" / "recovery-attempts"
        / f"{QUESTION_FORMAT_RECOVERY_ID}-question-heading-repair"
    )
    receipt_path = recovery_root / "receipt.json"
    if receipt_path.exists():
        receipt = _read_json(receipt_path)
        if (
            receipt.get("schema_version")
            != "adr-0114-question-heading-recovery-v1"
            or receipt.get("receipt_sha256") != _self_hash(
                receipt, "receipt_sha256"
            )
        ):
            raise BoundaryError("existing question-heading recovery receipt is invalid")
        return receipt

    experiment_path = adr / "실험/manifest.json"
    artifact_manifest_path = adr / "artifacts/manifest.json"
    experiment = _read_json(experiment_path)
    artifact_manifest = _read_json(artifact_manifest_path)
    active = next(run for run in experiment["runs"] if run["id"] == RUN_ID)
    if active.get("status") != "complete" or not paths["run"].is_file():
        raise BoundaryError("question heading recovery requires a completed run")
    artifact_rows = {
        str(row["path"]): deepcopy(dict(row))
        for row in artifact_manifest.get("files") or ()
    }
    question_map = {
        str(row["case_id"]): row for row in experiment.get("questions") or ()
    }
    if set(question_map) != set(CASE_IDS):
        raise BoundaryError("question heading recovery case coverage mismatch")

    def relative(path: Path) -> str:
        return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)

    question_receipts: list[dict[str, Any]] = []
    shard_receipts: list[dict[str, Any]] = []
    replacement_entries: dict[str, dict[str, Any]] = {}
    archive_entries: list[dict[str, Any]] = []
    repaired_question_sha: dict[str, str] = {}

    for case_id in CASE_IDS:
        entry = question_map[case_id]
        target = _expected_question_target(adr, entry)
        target_relative = relative(target)
        manifested = artifact_rows.get(target_relative)
        original_sha = str(entry.get("sha256") or "")
        if (
            manifested is None
            or manifested.get("sha256") != original_sha
            or manifested.get("contains_raw_prompts_and_outputs") is not True
        ):
            raise BoundaryError(f"question artifact lineage mismatch: {case_id}")
        archive = recovery_root / "original-questions" / target.name
        _archive_hardlink_once(target, archive, expected_sha256=original_sha)
        _rewrite_standard_question_headings(archive, target)
        repaired_sha = _sha256(target)
        repaired_question_sha[case_id] = repaired_sha
        question_receipts.append({
            "case_id": case_id,
            "target_path": target_relative,
            "original_path": relative(archive),
            "original_sha256": original_sha,
            "repaired_sha256": repaired_sha,
        })
        replacement_entries[target_relative] = _artifact_entry(
            target, str(manifested.get("description") or "question artifact"), True
        )
        archive_entries.append(_artifact_entry(
            archive, f"pre-repair immutable question artifact {case_id}", True
        ))
        entry["sha256"] = repaired_sha

    seal = _read_json(paths["seal"])
    public = _read_json(paths["public"])
    public_by_id = {
        str(row["case_id"]): row for row in public.get("cases") or ()
    }
    for case_id in CASE_IDS:
        target = _finalize_shard_file(paths, case_id)
        target_relative = relative(target)
        manifested = artifact_rows.get(target_relative)
        if manifested is None:
            raise BoundaryError(f"finalize shard is not manifested: {case_id}")
        original_sha = str(manifested.get("sha256") or "")
        archive = recovery_root / "original-finalize-shards" / target.name
        _archive_hardlink_once(target, archive, expected_sha256=original_sha)
        shard = _read_json(archive)
        if (
            shard.get("artifact_sha256")
            != _self_hash(shard, "artifact_sha256")
            or shard.get("question_sha256")
            != next(
                row["original_sha256"] for row in question_receipts
                if row["case_id"] == case_id
            )
        ):
            raise BoundaryError(f"original finalize shard is invalid: {case_id}")
        shard["question_sha256"] = repaired_question_sha[case_id]
        shard["artifact_sha256"] = _self_hash(shard, "artifact_sha256")
        _write_json(target, shard)
        _validate_finalize_shard(
            shard, expected_case=public_by_id[case_id],
            expected_question=question_map[case_id], seal=seal,
            paths=paths, adr=adr,
        )
        repaired_sha = _sha256(target)
        shard_receipts.append({
            "case_id": case_id,
            "target_path": target_relative,
            "original_path": relative(archive),
            "original_sha256": original_sha,
            "repaired_sha256": repaired_sha,
            "artifact_sha256": shard["artifact_sha256"],
        })
        replacement_entries[target_relative] = _artifact_entry(
            target, str(manifested.get("description") or "finalize shard")
        )
        archive_entries.append(_artifact_entry(
            archive, f"pre-repair immutable finalize shard {case_id}"
        ))

    receipt = {
        "schema_version": "adr-0114-question-heading-recovery-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "attempt_id": QUESTION_FORMAT_RECOVERY_ID,
        "status": "documentation_format_repaired_after_final_validation",
        "reason": "ADR-v4 required headings were merged or differently named",
        "semantic_payload_changed": False,
        "provider_calls": 0,
        "provider_replay_required": False,
        "product_capture_seal_sha256": _sha256(paths["seal"]),
        "run_artifact_sha256": _sha256(paths["run"]),
        "transformations": {
            "section_4": "split product-input and retrieval-stage headings",
            "sections_5_to_7": "rename headings to exact ADR-v4 labels",
        },
        "questions": question_receipts,
        "finalize_shards": shard_receipts,
        "completed_at": _now(),
    }
    receipt["receipt_sha256"] = _self_hash(receipt, "receipt_sha256")
    _write_json_once_or_same(receipt_path, receipt)

    updated_files = []
    for row in artifact_manifest.get("files") or ():
        updated_files.append(
            replacement_entries.get(str(row.get("path") or ""), deepcopy(dict(row)))
        )
    updated_files = _merge_artifact_entries(
        updated_files,
        archive_entries,
        [_artifact_entry(
            receipt_path,
            "post-finalization ADR-v4 question heading recovery receipt",
        )],
    )
    artifact_manifest["files"] = updated_files
    _write_json(artifact_manifest_path, artifact_manifest)

    attempts = active.setdefault("attempts", [])
    attempts.append({
        "id": QUESTION_FORMAT_RECOVERY_ID,
        "status": receipt["status"],
        "semantic_payload_changed": False,
        "provider_replay_required": False,
        "receipt_path": relative(receipt_path),
        "receipt_sha256": _sha256(receipt_path),
    })
    _write_json(experiment_path, experiment)
    return receipt


def finalize(
    public: Mapping[str, Any], scoring: Mapping[str, Any], paths: Mapping[str, Path],
    *, adr: Path = ADR, input_lock: Path = INPUT_LOCK,
    cm_source: Path = CM_SOURCE,
    prevalidated_seal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _read_json(adr / "실험/manifest.json")
    active = next(run for run in manifest["runs"] if run["id"] == RUN_ID)
    if active.get("status") == "complete":
        raise BoundaryError("completed run/final artifacts are immutable and cannot be overwritten")
    fixture = fixture_integrity_receipt(
        input_lock=input_lock, cm_source=cm_source,
        public_path=paths["public"], scoring_path=paths["scoring"],
    )
    if not fixture["ready"]:
        raise BoundaryError("finalize canonical fixture integrity failed")
    if prevalidated_seal is None:
        seal = validate_product_seal(
            paths["seal"], paths["public"], paths["captures"],
            metadata_only=True,
        )
    else:
        seal = dict(prevalidated_seal)
    _finalize_seal_receipts(seal, paths)
    question_map = {row["case_id"]: row for row in manifest["questions"]}
    shard_paths = _ensure_finalize_shards(
        public, paths, adr=adr, input_lock=input_lock, cm_source=cm_source,
    )
    rows: list[dict[str, Any]] = []
    graded_ledgers: list[dict[str, Any]] = []
    shard_ledger_hashes: dict[tuple[str, str], str] = {}
    reuse_existing_ledger = paths["ledger"].exists()
    for case, shard_path in zip(public["cases"], shard_paths):
        case_id = str(case["case_id"])
        shard = _read_json(shard_path)
        _validate_finalize_shard(
            shard, expected_case=case, expected_question=question_map[case_id],
            seal=seal, paths=paths, adr=adr,
        )
        question_map[case_id]["sha256"] = shard["question_sha256"]
        rows.append(deepcopy(shard["row"]))
        for arm in ARMS:
            shard_ledger_hashes[(case_id, arm)] = str(
                shard["graded_ledger_sha256"][arm]
            )
        if not reuse_existing_ledger:
            graded_ledgers.extend(deepcopy(shard["graded_ledgers"]))
        del shard
        _release_process_memory()
    if reuse_existing_ledger:
        existing_ledger = _read_json(paths["ledger"])
        if _existing_ledger_case_hashes(existing_ledger) != shard_ledger_hashes:
            raise BoundaryError("existing retrieval ledger differs from finalize shards")
        ledger_identity = {
            "artifact_sha256": existing_ledger["artifact_sha256"]
        }
        del existing_ledger
        _release_process_memory()
    else:
        declared = {
            arm: [row["stage_id"] for row in STAGE_PLAN[arm]] for arm in ARMS
        }
        run_ledger = ledger.build_run_artifact(RUN_ID, graded_ledgers, declared)
        experiment_ledger = ledger.build_experiment_artifact(
            ADR_ID, EXPERIMENT_ID, [run_ledger]
        )
        _write_json_once_or_same(paths["ledger"], experiment_ledger)
        ledger_identity = {
            "artifact_sha256": experiment_ledger["artifact_sha256"]
        }
        del run_ledger, experiment_ledger, graded_ledgers
        _release_process_memory()
    summary = _summarize(rows, ledger_identity)
    run_artifact = {
        "schema_version": "adr-0114-integrated-golden-61-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "input_lock_sha256": EXPECTED_INPUT_LOCK_SHA256,
        "product_seal_path": str(paths["seal"].relative_to(ROOT)),
        "product_seal_sha256": _sha256(paths["seal"]),
        "gold_opened_after_product_seal": True,
        "models": {"product": MODEL, "offline_paired_judge": MODEL},
        "summary": summary,
        "rows": rows,
        "completed_at": (
            _read_json(paths["run"]).get("completed_at")
            if paths["run"].exists() else _now()
        ),
    }
    run_artifact["artifact_sha256"] = _self_hash(run_artifact, "artifact_sha256")
    _write_json_once_or_same(paths["run"], run_artifact)

    active.update({"status": "complete", "sha256": _sha256(paths["run"])})
    manifest["retrieval_accounting"].update({
        "corpus_total": summary["corpus_article_roots"],
        "before_filter": {
            arm: summary["by_arm"][arm]["before_filter_total"] for arm in ARMS
        },
        "after_filter": {
            arm: summary["by_arm"][arm]["after_filter_total"] for arm in ARMS
        },
        "presented_total": {
            arm: summary["by_arm"][arm]["presented_total"] for arm in ARMS
        },
        "presented_mean": {
            arm: summary["by_arm"][arm]["presented_mean"] for arm in ARMS
        },
        "presented_p50": {
            arm: summary["by_arm"][arm]["presented_p50"] for arm in ARMS
        },
        "presented_p95": {
            arm: summary["by_arm"][arm]["presented_p95"] for arm in ARMS
        },
        "golden_recall": {
            arm: summary["by_arm"][arm]["decisive_golden_recall"] for arm in ARMS
        },
        "selectivity": {arm: summary["by_arm"][arm]["selectivity"] for arm in ARMS},
    })
    manifest["retrieval_accounting"]["stage_ledger"]["sha256"] = _sha256(paths["ledger"])
    manifest["results"] = {
        "status": "complete",
        "by_arm": summary["by_arm"],
        "comparisons": [{"candidate_vs_baseline": summary["paired_outcomes"], "delta": summary["paired_delta"]}],
        "judge_disagreements": summary["judge_paired_label_disagreements"],
        "usage": {
            **{arm: summary["by_arm"][arm]["product_usage"] for arm in ARMS},
            "offline_paired_judge": summary["judge_usage"],
        },
        "latency": {
            **{arm: {
                "product_p50_ms": summary["by_arm"][arm]["product_wall_ms_p50"],
                "product_p95_ms": summary["by_arm"][arm]["product_wall_ms_p95"],
                "provider_p50_ms": summary["by_arm"][arm]["provider_call_ms_p50"],
                "provider_p95_ms": summary["by_arm"][arm]["provider_call_ms_p95"],
            } for arm in ARMS},
            "offline_paired_judge": {"p50_ms": summary["judge_p50_ms"], "p95_ms": summary["judge_p95_ms"]},
        },
        "error_taxonomy": summary["error_taxonomy"],
    }
    files = [
        _artifact_entry(paths["public"], "gold-free public question-only fixture"),
        _artifact_entry(paths["scoring"], "offline-only reference, decisive, and required-companion fixture"),
        _artifact_entry(paths["seal"], "hash seal over all product captures"),
        _artifact_entry(paths["ledger"], "retrieval-stage-ledger-v1 for both arms"),
        _artifact_entry(paths["run"], "paired answer/retrieval run aggregate", True),
    ]
    files.extend(
        _artifact_entry(_capture_file(paths["captures"], case_id), f"sealed product capture {case_id}", True)
        for case_id in CASE_IDS
    )
    files.extend(
        _artifact_entry(paths["judges"] / f"{case_id}.json", f"paired Haiku judge receipt {case_id}", True)
        for case_id in CASE_IDS
    )
    files.extend(
        _artifact_entry(
            _finalize_shard_file(paths, case_id),
            f"recovery-safe compact finalize shard {case_id}",
        )
        for case_id in CASE_IDS
    )
    files.extend(
        _artifact_entry(
            adr / "실험" / question_map[case_id]["file"],
            f"question-level raw prompts, outputs, evidence, and grading {case_id}",
            True,
        )
        for case_id in CASE_IDS
    )
    artifact_manifest_path = adr / "artifacts/manifest.json"
    old = _read_json(artifact_manifest_path) if artifact_manifest_path.exists() else {}
    files = _merge_artifact_entries(
        _validated_existing_artifact_entries(old),
        _failed_attempt_entries(adr),
        files,
    )
    artifact_manifest = {
        "schema_version": "adr-artifacts-v1",
        "adr_id": ADR_ID,
        "created_at": old.get("created_at") or _now(),
        "files": files,
    }
    _write_json(artifact_manifest_path, artifact_manifest)
    # The experiment manifest is the final commit marker.  A completed run can
    # never point at an artifact manifest that has not yet been written.
    _write_json(adr / "실험/manifest.json", manifest)
    return run_artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, default=ADR)
    parser.add_argument("--input-lock", type=Path, default=INPUT_LOCK)
    parser.add_argument("--cm-source", type=Path, default=CM_SOURCE)
    parser.add_argument("--prepare-fixtures", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--retrieval-only", action="store_true",
        help=(
            "grade whether every expected article reached the final present "
            "stage; skip the offline semantic judge"
        ),
    )
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument(
        "--finalize-case", choices=CASE_IDS, help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--repair-question-headings", action="store_true",
        help="repair ADR-v4 question headings without replaying providers",
    )
    args = parser.parse_args(argv)
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    input_lock = args.input_lock if args.input_lock.is_absolute() else ROOT / args.input_lock
    cm_source = args.cm_source if args.cm_source.is_absolute() else ROOT / args.cm_source
    paths = _artifact_paths(adr)

    if args.repair_question_headings:
        recovery_lock = _acquire_run_lock(adr)
        try:
            receipt = repair_question_heading_artifacts(adr=adr, paths=paths)
        finally:
            recovery_lock.close()
        print(json.dumps({
            "attempt_id": receipt["attempt_id"],
            "status": receipt["status"],
            "receipt_sha256": receipt["receipt_sha256"],
        }, ensure_ascii=False, sort_keys=True))
        return 0
    if args.finalize_case:
        receipt = materialize_finalize_shard(
            args.finalize_case, adr=adr, paths=paths,
        )
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    if args.prepare_fixtures:
        receipt = prepare_fixtures(
            input_lock=input_lock, cm_source=cm_source,
            public_path=paths["public"], scoring_path=paths["scoring"],
        )
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    if args.preflight_only:
        receipt = preflight_receipt(
            adr=adr, input_lock=input_lock, cm_source=cm_source
        )
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0 if receipt["status"] == "ready" else 1

    run_lock = _acquire_run_lock(adr)
    manifest = _read_json(adr / "실험/manifest.json")
    active = next(run for run in manifest["runs"] if run["id"] == RUN_ID)
    if active.get("status") == "complete":
        raise BoundaryError("completed run/final artifacts are immutable")
    if args.retrieval_only:
        if paths["retrieval_only"].exists() and not args.resume:
            raise BoundaryError("existing retrieval-only report requires --resume")
    elif (paths["run"].exists() or paths["ledger"].exists()) and not args.resume:
        raise BoundaryError("partial finalization artifacts require --resume")
    preflight = preflight_receipt(
        adr=adr, input_lock=input_lock, cm_source=cm_source
    )
    if preflight["status"] != "ready":
        raise BoundaryError(
            "normal-run preflight is blocked; canonical fixtures, frozen manifest "
            "stage plan, input locks, and runtime adapter must all match: "
            f"{json.dumps(preflight, ensure_ascii=False, sort_keys=True)}"
        )
    public = _read_json(paths["public"])
    _forbid_product_gold(public)
    if [row.get("case_id") for row in public.get("cases") or ()] != list(CASE_IDS):
        raise BoundaryError("public question fixture is not frozen Golden 61")
    contract = runtime_adapter_contract()
    if not contract["ready"]:
        raise RuntimeContractError(f"integrated runtime is not wired: {contract}")

    resume_seal = None
    if not (args.resume and paths["seal"].exists()):
        run_products(public, paths, workers=args.workers, resume=args.resume)
    else:
        resume_seal = validate_product_seal(
            paths["seal"], paths["public"], paths["captures"],
            metadata_only=True,
        )
    scoring = open_scoring_fixture(
        paths["scoring"], paths["seal"], paths["public"], paths["captures"],
        input_lock=input_lock, cm_source=cm_source,
        metadata_only=args.resume,
        prevalidated_seal=resume_seal,
    )
    if args.retrieval_only:
        report = write_retrieval_only_report(
            public, scoring, paths, prevalidated_seal=resume_seal,
        )
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        run_lock.close()
        return 0
    run_judges(
        public, scoring, paths, workers=args.workers, resume=args.resume,
        prevalidated_seal=resume_seal,
    )
    run = finalize(
        public, scoring, paths, adr=adr,
        input_lock=input_lock, cm_source=cm_source,
        prevalidated_seal=resume_seal,
    )
    print(json.dumps(run["summary"], ensure_ascii=False, indent=2))
    run_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
