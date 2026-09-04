#!/usr/bin/env python3
"""ADR-0138 deterministic, research-only law-family early-entry experiment.

The command boundary is deliberate:

* freeze-input reads only ADR-0114 gold-free public captures.
* run-product reads only the derived ADR-0138 input lock and sealed code.
* score first validates the new ADR-0138 product seal, then opens gold.

No command constructs an LLM, judge, answer compiler, runtime registry, or MAIN
promotion path.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for _key, _relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core.rag import integrated_legal_research as integrated_research  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402
from lawrag.core.rag.legal_research_llm_selector import (  # noqa: E402
    branches_from_query_plan,
)
from lawrag.core.rag.legal_system_entry import (  # noqa: E402
    LegalSystemEntryPlanner as BaselinePlanner,
)
from lawrag.core.rag.legal_system_map import (  # noqa: E402
    load_legal_system_runtime,
)


ADR_ID = "ADR-0138"
EXPERIMENT_ID = "ADR-0138-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "law-family-entry"
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
PRESENT_CAP = 28
INSTRUMENT_LIMIT = 8
ENTRY_LIMIT = 12
POINTS_PER_INSTRUMENT = 6
FAMILY_SIGNAL_PREFIX = "HELD_LAW_FAMILY_ROUTING_HINT:"

ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0138-law-family-early-entry-retrieval"
EXPERIMENT_MANIFEST = ADR / "실험/manifest.json"
ARTIFACTS = ADR / "artifacts"
INPUT_LOCK = ARTIFACTS / "input-lock-v2.json"
PRODUCT_CAPTURE_DIR = ARTIFACTS / "product-captures/run-001"
PRODUCT_SEAL = ARTIFACTS / "product-capture-seal-run-001.json"
LEDGER_ARTIFACT = ARTIFACTS / "retrieval-stage-ledger-run-001.json"
RUN_ARTIFACT = ARTIFACTS / "run-001.json"
QUESTION_INDEX = ARTIFACTS / "question-index-run-001.json"

UPSTREAM_ADR = (
    ROOT
    / "docs/adr/ADR-0114-integrated-legal-research-state-machine-golden-61"
)
PUBLIC_FIXTURE = UPSTREAM_ADR / "artifacts/public-questions-run-001.json"
UPSTREAM_SEAL = UPSTREAM_ADR / "artifacts/product-capture-seal-run-001.json"
SCORING_FIXTURE = UPSTREAM_ADR / "artifacts/scoring-fixture-run-001.json"
QUERY_PLAN_POINTER = (
    "/arms/integrated-seven-layer/retrieval/meta/"
    "integrated_research/query_plan"
)

CANDIDATE_ROOT = (
    Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0138/law-family-entry"
)
CANDIDATE_MANIFEST = CANDIDATE_ROOT / "candidate.json"
CANDIDATE_REVISION = (
    CANDIDATE_ROOT
    / "revisions/rev-001/snapshot/lawrag/core/rag/legal_system_entry.py"
)
CANDIDATE_MANIFEST_SHA256 = (
    "17971d9cbcedd4e4126cd67af07585a98292dd07e152aa79d40ea7aae4b69bbc"
)
CANDIDATE_REVISION_ID = "rev-001"
CANDIDATE_REVISION_SHA256 = (
    "3ff54611f1864b89f3b2efca57917508ece47b92554c714c3eac14b8c13ead17"
)
CANDIDATE_FILE_SHA256 = (
    "700371c5254119bfdf7ff613ff1201c4518ab96d6de9ea7316b83c2c4fdc1880"
)

UPSTREAM_PUBLIC_SHA256 = (
    "e9c280f9695d492a5389c397cb6d6a48e15f8f32149113eef5cfc5f4a22545e2"
)
UPSTREAM_SEAL_FILE_SHA256 = (
    "6d3f3a9dbf3ff72686913bfa550ef4a8151c100ca463d301080bb15197ea2ceb"
)
UPSTREAM_SEAL_CONTENT_SHA256 = (
    "fd6a2e4403dcf828d97f32f1c3ea6b198582685f2e72c8378273c68967feec47"
)
SCORING_SHA256 = (
    "cee5da071c65ee7bb59db908896d9eed57ea0767b6d5a7e2e40a4cb63d80f4a2"
)

CASE_IDS = tuple(
    [f"cm-{number:03d}" for number in range(1, 52)]
    + [f"fsc-hard-{number:03d}" for number in range(1, 11)]
)

SOURCE_HASHES = {
    "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger/"
    "artifacts/input-lock.json":
        "7636cc52ac0bd94a10baa1d75f3f381940981ff86beafa7f7ee91fedf9308452",
    "data/review/cm_core_e2e_v2.json":
        "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    "data/review/fsc_hard_retrieval_v2.json":
        "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
    "01_DATA/law_index.json":
        "5c781a916daceb49e494790228154954ab78d053fab9ca76bd8488a117536791",
    "data/legal_system/legal-system-map-v1.json":
        "627d2a27631bf4c8e51e608b153cdf5fb2f5f880b881499c158f87018ed10d9d",
    "data/legal_graph/CURRENT.json":
        "418571f80d6d49ecdab9e8c2c6e2bede7221e5836f2a3a567100ee861c0c9161",
    "lawrag/core/rag/index.py":
        "49b8ec4ab21ece639492f25d3802895abea1de1f0855f629ebbfc3611497f564",
    "lawrag/core/rag/legal_coordinates.py":
        "bbdb1480d3ed6780d1cad41bede46c524b36604554ed2d6ea0ee4c22c2e059df",
    "lawrag/core/rag/legal_graph_store.py":
        "f8ba0e0495fa18771dc25c2e93c72f0d2945fdfdb1f2a1deaf56f260b8cde9ed",
    "lawrag/core/rag/legal_instrument_routing.py":
        "df7d73d1c193636b6c299b6643c96b582d30260fca10a05ff4bc85c289e3bc2b",
    "lawrag/core/rag/legal_research_atlas.py":
        "908d9ad40e4888c58b8c8fd074beb1774851a5ae2d5d4b7df62314524e3920f7",
    "lawrag/core/rag/legal_system_entry.py":
        "a483cc384e3d3adefbd6d8ec1394415ffc7661a6ca219b6bfe26782a3f7e4786",
    "lawrag/core/rag/legal_system_map.py":
        "35c92afd6ba051997db901eb32beb307636d5a03f4fa33d5ea45a81eac0d38b3",
    "lawrag/core/rag/legal_research_llm_selector.py":
        "61b6e5201c6f6fee6899cc82432881729f8eb3cbb2672cc0c898daf45e4c769d",
    "lawrag/core/rag/experiments/retrieval_stage_ledger.py":
        "a4dbfb0c97c0f311ed2642f31f6340b761c1da68e60443407d203284f60b6357",
    "lawrag/core/rag/integrated_legal_research.py":
        "0c075bc49810837bf96048a8c309000a8eafc39b25d4c309260700314bc99c8e",
    "scripts/rag_integrated_legal_research_golden_61.py":
        "f8a0fc2438048ec1146ae7997e6b4c190f1e37e15e977ed2643fc5ea4f28ffc9",
}

EXPECTED_RESOURCE = {
    "authority_as_of": "20260827",
    "authority_generation":
        "c5e1d95d187055fb425e4bf3f7ed7aa1fd40b30d0468f50aa3b9a135893f3666",
    "corpus_fingerprint":
        "211f5337825fb87516ba348c0195ff212198aa12342e6daf6a3505e67298f447",
    "law_index_sha256":
        "5c781a916daceb49e494790228154954ab78d053fab9ca76bd8488a117536791",
    "profiles_sha256":
        "5a5e24a5aaea51ee186f2992a63d600fdc27465fcff0eb4bda2407a77fa06a9c",
    "legal_graph_content_sha256":
        "505d1c9faf6bb4a3d92d298b9acb3cf62dfd50924843283a60e7a2eb507e2285",
    "legal_graph_pointer_sha256":
        "418571f80d6d49ecdab9e8c2c6e2bede7221e5836f2a3a567100ee861c0c9161",
    "runtime_input_fingerprint":
        "f3627c40ea1efd7e78b68ad1ca0600de9d373af57151c5825e7ca1a7c6070d3e",
    "run_environment_hash":
        "79ddb287e49fb85ac11c9de00604bd873529d865848d3d44152bf1cdd433f2e1",
}

STAGE_PLAN = (
    ("question-source", "source", ()),
    ("current-entry-retrieve", "retrieve", ("question-source",)),
    (
        "held-law-family-rerank",
        "rerank",
        ("current-entry-retrieve",),
    ),
    ("entry-cap-select", "select", ("held-law-family-rerank",)),
    ("entry-present", "present", ("entry-cap-select",)),
)
STAGE_IDS = tuple(row[0] for row in STAGE_PLAN)


class BoundaryError(RuntimeError):
    """Raised when an experiment boundary or frozen hash is violated."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise BoundaryError(f"JSON root must be an object: {path}")
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=ledger.canonical_json)
    return value


def _json_file_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _content_hash(value: Mapping[str, Any], field: str) -> str:
    return ledger.deterministic_sha256(
        {key: deepcopy(item) for key, item in value.items() if key != field}
    )


def _attach_hash(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = _content_hash(value, field)
    return value


def _write_json(
    path: Path,
    value: Mapping[str, Any],
    *,
    immutable: bool = False,
) -> None:
    payload = (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    if path.exists() and immutable:
        existing = path.read_text("utf-8")
        if existing == payload:
            return
        raise BoundaryError(f"immutable artifact already differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, "utf-8")
    temporary.replace(path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, "utf-8")
    temporary.replace(path)


def _repo_path(raw: str) -> Path:
    target = (ROOT / raw).resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise BoundaryError(f"path escapes repository: {raw}")
    return target


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def _assert_file_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise BoundaryError(f"{label} is missing: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise BoundaryError(
            f"{label} hash mismatch: expected={expected}, actual={actual}"
        )


def _percentile(values: Iterable[float], fraction: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    index = max(0, min(len(rows) - 1, math.ceil(fraction * len(rows)) - 1))
    return round(rows[index], 6)


def _assert_source_hashes() -> None:
    for raw, expected in SOURCE_HASHES.items():
        _assert_file_hash(_repo_path(raw), expected, raw)
    _assert_file_hash(
        PUBLIC_FIXTURE, UPSTREAM_PUBLIC_SHA256, "ADR-0114 public fixture"
    )
    _assert_file_hash(
        UPSTREAM_SEAL, UPSTREAM_SEAL_FILE_SHA256, "ADR-0114 product seal"
    )


def _branch_row(branch: Any) -> dict[str, Any]:
    return {
        "branch_id": str(branch.branch_id),
        "issue_axis": str(branch.issue_axis),
        "preferred_roles": [
            getattr(role, "value", str(role)) for role in branch.preferred_roles
        ],
        "topic_hints": [str(value) for value in branch.topic_hints],
        "preferred_instrument_ids": [
            str(value) for value in branch.preferred_instrument_ids
        ],
        "required": bool(branch.required),
    }


def _forbid_scoring_payload(value: Any, *, path: str = "input") -> None:
    forbidden = {
        "gold_articles",
        "required_companions",
        "reference_answer",
        "expected_articles",
        "answer",
        "judge",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in forbidden:
                raise BoundaryError(f"scoring field {key!r} found at {path}")
            _forbid_scoring_payload(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _forbid_scoring_payload(item, path=f"{path}[{index}]")


def _validate_upstream_seal(
    public: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    seal = _read_json(UPSTREAM_SEAL)
    if seal.get("schema_version") != "adr-0114-product-capture-seal-v1":
        raise BoundaryError("ADR-0114 seal schema mismatch")
    if seal.get("seal_sha256") != UPSTREAM_SEAL_CONTENT_SHA256:
        raise BoundaryError("ADR-0114 embedded seal hash mismatch")
    if seal.get("seal_sha256") != _content_hash(seal, "seal_sha256"):
        raise BoundaryError("ADR-0114 seal canonical hash mismatch")
    if (
        seal.get("gold_visible_to_product") is not False
        or seal.get("public_fixture_sha256") != UPSTREAM_PUBLIC_SHA256
        or seal.get("case_count") != len(CASE_IDS)
    ):
        raise BoundaryError("ADR-0114 seal identity mismatch")

    public_cases = list(public.get("cases") or ())
    if [row.get("case_id") for row in public_cases] != list(CASE_IDS):
        raise BoundaryError("public fixture case order mismatch")
    public_by_id = {str(row["case_id"]): row for row in public_cases}

    receipts = list(seal.get("case_receipts") or ())
    if [row.get("case_id") for row in receipts] != list(CASE_IDS):
        raise BoundaryError("ADR-0114 seal receipt order mismatch")
    captures: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        case_id = str(receipt["case_id"])
        path = _repo_path(str(receipt["path"]))
        _assert_file_hash(path, str(receipt["sha256"]), f"capture {case_id}")
        capture = _read_json(path)
        if capture.get("capture_sha256") != _content_hash(
            capture, "capture_sha256"
        ):
            raise BoundaryError(f"capture canonical hash mismatch: {case_id}")
        expected = public_by_id[case_id]
        question = str(expected["question"])
        if (
            capture.get("case_id") != case_id
            or capture.get("complete") is not True
            or capture.get("gold_visible_to_product") is not False
            or capture.get("question") != question
            or receipt.get("capture_sha256") != capture.get("capture_sha256")
            or receipt.get("question_sha256")
            != hashlib.sha256(question.encode("utf-8")).hexdigest()
        ):
            raise BoundaryError(f"capture identity mismatch: {case_id}")
        captures[case_id] = capture
    return seal, captures


def freeze_input() -> None:
    _assert_source_hashes()
    public = _read_json(PUBLIC_FIXTURE)
    if (
        public.get("schema_version")
        != "adr-0114-public-questions-v1"
        or public.get("gold_visible_to_product") is not False
    ):
        raise BoundaryError("public fixture schema/boundary mismatch")
    seal, captures = _validate_upstream_seal(public)
    public_cases = list(public["cases"])
    receipts = {
        str(row["case_id"]): row for row in seal["case_receipts"]
    }

    cases: list[dict[str, Any]] = []
    closed_preferred_count = 0
    for public_case in public_cases:
        case_id = str(public_case["case_id"])
        capture = captures[case_id]
        integrated = (
            capture["arms"]["integrated-seven-layer"]["retrieval"]["meta"][
                "integrated_research"
            ]
        )
        query_plan = deepcopy(integrated.get("query_plan"))
        if not isinstance(query_plan, dict):
            raise BoundaryError(f"query plan is missing: {case_id}")
        branches = [
            _branch_row(branch) for branch in branches_from_query_plan(query_plan)
        ]
        closed_preferred_count += sum(
            len(branch["preferred_instrument_ids"]) for branch in branches
        )
        receipt = receipts[case_id]
        question = str(public_case["question"])
        cases.append(
            {
                "number": int(public_case["number"]),
                "case_id": case_id,
                "suite": str(public_case["suite"]),
                "question": question,
                "question_sha256": hashlib.sha256(
                    question.encode("utf-8")
                ).hexdigest(),
                "source_capture_path": str(receipt["path"]),
                "source_capture_file_sha256": str(receipt["sha256"]),
                "source_capture_sha256": str(receipt["capture_sha256"]),
                "query_plan": query_plan,
                "query_plan_json_pointer": QUERY_PLAN_POINTER,
                "query_plan_sha256": ledger.deterministic_sha256(query_plan),
                "branches": branches,
                "branches_sha256": ledger.deterministic_sha256(branches),
            }
        )

    resource = {
        key: seal["runtime_preload"].get(key) for key in EXPECTED_RESOURCE
    }
    if resource != EXPECTED_RESOURCE:
        raise BoundaryError("upstream resource admission receipt mismatch")
    source_receipts = [
        {"path": raw, "sha256": expected}
        for raw, expected in sorted(SOURCE_HASHES.items())
    ]
    source_receipts.extend(
        [
            {
                "path": _relative(PUBLIC_FIXTURE),
                "sha256": UPSTREAM_PUBLIC_SHA256,
            },
            {
                "path": _relative(UPSTREAM_SEAL),
                "sha256": UPSTREAM_SEAL_FILE_SHA256,
                "content_sha256": UPSTREAM_SEAL_CONTENT_SHA256,
            },
        ]
    )
    value = {
        "schema_version": "adr-0138-early-entry-input-v2",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "selection_rule": (
            "ADR-0114 sealed cm-001..cm-051 and fsc-hard-001..010, "
            "in original order, with no result-based selection"
        ),
        "case_count": len(cases),
        "gold_visible_to_product": False,
        "query_plan_source_pointer": QUERY_PLAN_POINTER,
        "closed_preferred_instrument_occurrences": closed_preferred_count,
        "source_receipts": source_receipts,
        "resource_admission": resource,
        "scoring_contract": {
            "product_access": "forbidden-before-valid-adr-0138-product-seal",
            "expected_file_sha256": SCORING_SHA256,
            "opened_during_input_freeze": False,
        },
        "cases": cases,
    }
    _forbid_scoring_payload(value)
    _attach_hash(value, "artifact_sha256")
    _write_json(INPUT_LOCK, value, immutable=True)
    print(
        json.dumps(
            {
                "input_lock": _relative(INPUT_LOCK),
                "file_sha256": _sha256(INPUT_LOCK),
                "content_sha256": value["artifact_sha256"],
                "cases": len(cases),
                "closed_preferred_instrument_occurrences":
                    closed_preferred_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _validate_input_lock(*, require_manifest_hash: bool) -> dict[str, Any]:
    value = _read_json(INPUT_LOCK)
    if value.get("schema_version") != "adr-0138-early-entry-input-v2":
        raise BoundaryError("ADR-0138 input lock schema mismatch")
    if value.get("artifact_sha256") != _content_hash(
        value, "artifact_sha256"
    ):
        raise BoundaryError("ADR-0138 input lock content hash mismatch")
    if (
        value.get("adr_id") != ADR_ID
        or value.get("experiment_id") != EXPERIMENT_ID
        or value.get("run_id") != RUN_ID
        or value.get("gold_visible_to_product") is not False
        or value.get("case_count") != len(CASE_IDS)
    ):
        raise BoundaryError("ADR-0138 input lock identity mismatch")
    _forbid_scoring_payload(value)
    cases = list(value.get("cases") or ())
    if [row.get("case_id") for row in cases] != list(CASE_IDS):
        raise BoundaryError("ADR-0138 input case order mismatch")
    for case in cases:
        question = str(case.get("question") or "")
        query_plan = case.get("query_plan")
        if (
            case.get("question_sha256")
            != hashlib.sha256(question.encode("utf-8")).hexdigest()
            or not isinstance(query_plan, dict)
            or case.get("query_plan_sha256")
            != ledger.deterministic_sha256(query_plan)
        ):
            raise BoundaryError(
                f"input case hash mismatch: {case.get('case_id')}"
            )
        branches = [
            _branch_row(branch) for branch in branches_from_query_plan(query_plan)
        ]
        if (
            case.get("branches") != branches
            or case.get("branches_sha256")
            != ledger.deterministic_sha256(branches)
        ):
            raise BoundaryError(
                f"input branch hash mismatch: {case.get('case_id')}"
            )
    if require_manifest_hash:
        manifest = _read_json(EXPERIMENT_MANIFEST)
        dataset = manifest.get("dataset") or {}
        if (
            dataset.get("frozen_source") != _relative(INPUT_LOCK)
            or dataset.get("sha256") != _sha256(INPUT_LOCK)
        ):
            raise BoundaryError(
                "ADR manifest has not frozen the ADR-0138 input-lock hash"
            )
    return value


def _validate_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    _assert_file_hash(
        CANDIDATE_MANIFEST,
        CANDIDATE_MANIFEST_SHA256,
        "ADR-0138 candidate manifest",
    )
    manifest = _read_json(CANDIDATE_MANIFEST)
    if (
        manifest.get("schema_version") != "adr-code-candidate-v1"
        or manifest.get("adr_id") != ADR_ID
        or manifest.get("experiment_id") != EXPERIMENT_ID
        or manifest.get("arm_id") != CANDIDATE_ARM
        or manifest.get("run_ids") != [RUN_ID]
        or manifest.get("status") != "research-only"
        or manifest.get("production_loadable") is not False
    ):
        raise BoundaryError("candidate identity/isolation mismatch")
    revisions = list(manifest.get("revisions") or ())
    if not revisions:
        raise BoundaryError("candidate has no frozen revision")
    revision = revisions[-1]
    if (
        revision.get("revision_id") != CANDIDATE_REVISION_ID
        or revision.get("revision_sha256") != CANDIDATE_REVISION_SHA256
    ):
        raise BoundaryError("candidate revision linkage mismatch")
    files = list(revision.get("files") or ())
    if len(files) != 1:
        raise BoundaryError("candidate revision must contain one source file")
    if _repo_path(str(files[0]["frozen_path"])) != CANDIDATE_REVISION:
        raise BoundaryError("candidate frozen path mismatch")
    if files[0].get("snapshot_sha256") != CANDIDATE_FILE_SHA256:
        raise BoundaryError("candidate frozen file receipt mismatch")
    _assert_file_hash(
        CANDIDATE_REVISION,
        CANDIDATE_FILE_SHA256,
        "candidate frozen source",
    )
    return manifest, revision


def _validate_adr_pre_run(input_lock: Mapping[str, Any]) -> None:
    manifest = _read_json(EXPERIMENT_MANIFEST)
    design = manifest.get("design") or {}
    isolation = design.get("code_isolation") or {}
    candidates = list(isolation.get("candidates") or ())
    if (
        manifest.get("adr_id") != ADR_ID
        or manifest.get("experiment_id") != EXPERIMENT_ID
        or design.get("criteria_frozen_before_run") is not True
        or (manifest.get("llm_policy") or {}).get("llm_calls") != []
        or isolation.get("mode") != "candidate_snapshot"
        or isolation.get("production_paths_modified_before_decision") is not False
        or isolation.get("runtime_import_allowed") is not False
        or isolation.get("production_registry_registered") is not False
        or isolation.get("main_wiring_unchanged") is not True
        or len(candidates) != 1
    ):
        raise BoundaryError("ADR-0138 pre-run isolation contract mismatch")
    candidate = candidates[0]
    runner_path = ROOT / str(candidate.get("runner_path") or "")
    if (
        candidate.get("manifest_sha256") != CANDIDATE_MANIFEST_SHA256
        or candidate.get("revision_id") != CANDIDATE_REVISION_ID
        or candidate.get("revision_sha256") != CANDIDATE_REVISION_SHA256
        or runner_path.resolve() != Path(__file__).resolve()
        or candidate.get("runner_sha256") != _sha256(Path(__file__))
        or (manifest.get("dataset") or {}).get("sha256")
        != _sha256(INPUT_LOCK)
        or input_lock.get("artifact_sha256")
        != _content_hash(input_lock, "artifact_sha256")
    ):
        raise BoundaryError("ADR-0138 concrete code/data hashes are not frozen")


def preflight() -> None:
    _assert_source_hashes()
    input_lock = _validate_input_lock(require_manifest_hash=True)
    _validate_candidate()
    _validate_adr_pre_run(input_lock)
    _, _, preload_ms, corpus_total, live_resource = _load_runtime()
    if live_resource != input_lock.get("resource_admission"):
        raise BoundaryError("preflight runtime differs from frozen input lock")
    print(
        json.dumps(
            {
                "status": "ready",
                "cases": len(input_lock["cases"]),
                "preload_ms": preload_ms,
                "corpus_article_roots": corpus_total,
                "provider_calls": 0,
                "llm_calls": 0,
                "candidate_revision": CANDIDATE_REVISION_ID,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _load_candidate_planner() -> type[Any]:
    source_bytes = CANDIDATE_REVISION.read_bytes()
    actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha256 != CANDIDATE_FILE_SHA256:
        raise BoundaryError(
            "candidate frozen source changed before direct import: "
            f"expected={CANDIDATE_FILE_SHA256}, actual={actual_sha256}"
        )
    module_name = "lawrag.core.rag._adr0138_rev001_legal_system_entry"
    spec = importlib.util.spec_from_loader(
        module_name, loader=None, origin=str(CANDIDATE_REVISION)
    )
    if spec is None:
        raise BoundaryError("cannot construct candidate module spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        code = compile(
            source_bytes,
            str(CANDIDATE_REVISION),
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)
    finally:
        sys.modules.pop(module_name, None)
    planner = getattr(module, "LegalSystemEntryPlanner", None)
    if not isinstance(planner, type):
        raise BoundaryError("candidate planner class is missing")
    return planner


def _corpus_fingerprint(index: Any) -> str:
    """Hash the exact scoped search corpus and deterministic entry data."""

    digest = hashlib.sha256()

    def update(value: Any) -> None:
        digest.update(_json_file_bytes(value))

    update(
        {
            "authority_generation": str(index.authority_generation),
            "authority_as_of": str(index.authority_as_of),
            "scope": sorted(index.scope) if index.scope is not None else None,
            "canonical_doc_ids": sorted(index.canonical_doc_ids or ()),
            "saved_links": index.saved_links,
            "rel_fixes": index.rel_fixes,
        }
    )
    for entry in sorted(
        index.entries,
        key=lambda row: (
            row.doc_id,
            -1 if row.node is None else int(row.node),
            row.kind,
            row.key,
            row.target,
        ),
    ):
        update(asdict(entry))
    for doc_id, view in sorted(index.entry_docs.items()):
        update(
            {
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
            }
        )
    return digest.hexdigest()


def _load_runtime() -> tuple[Any, Any, float, int, dict[str, Any]]:
    started = time.perf_counter()
    index = index_mod.current().scoped(None)
    preload = integrated_research.preload_resources(index)
    preload["corpus_fingerprint"] = _corpus_fingerprint(index)
    environment = {
        key: value
        for key, value in preload.items()
        if key not in {"elapsed_ms", "provider_calls", "run_environment_hash"}
    }
    preload["run_environment_hash"] = ledger.deterministic_sha256(
        _jsonable(environment)
    )
    runtime = load_legal_system_runtime(index, semantic_cards=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    system_map = runtime.system_map
    graph = system_map.legal_graph
    live_resource = {
        key: preload.get(key) for key in EXPECTED_RESOURCE
    }
    if (
        live_resource != EXPECTED_RESOURCE
        or str(index.authority_as_of) != preload.get("authority_as_of")
        or str(index.authority_generation)
        != preload.get("authority_generation")
        or system_map.law_index_sha256
        != preload.get("law_index_sha256")
        or system_map.profiles_sha256
        != preload.get("profiles_sha256")
        or graph.content_sha256
        != preload.get("legal_graph_content_sha256")
        or graph.current_sha256
        != preload.get("legal_graph_pointer_sha256")
    ):
        raise BoundaryError("live resource generation differs from frozen admission")
    corpus_total = sum(
        node.get("family") == "kr_article"
        and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items()
    )
    if corpus_total < 1:
        raise BoundaryError("current corpus has no article roots")
    return index, runtime, round(elapsed_ms, 6), corpus_total, live_resource


def _normalized(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _strong_anchors(
    runtime: Any,
    question: str,
    branches: Sequence[Any],
) -> tuple[list[str], list[str]]:
    question_norm = _normalized(question)
    preferred = {
        str(instrument_id)
        for branch in branches
        for instrument_id in branch.preferred_instrument_ids
    }
    explicit: list[str] = []
    closed: list[str] = []
    profiles = runtime.system_map.profile_by_id
    for instrument in runtime.atlas.instruments:
        profile = profiles.get(instrument.instrument_id)
        if profile is None or not profile.law_families:
            continue
        name_norm = _normalized(instrument.name)
        if name_norm and name_norm in question_norm:
            explicit.append(instrument.instrument_id)
        if instrument.instrument_id in preferred:
            closed.append(instrument.instrument_id)
    return sorted(set(explicit)), sorted(set(closed))


def _flatten_plans(
    index: Any,
    plans: Sequence[Any],
    canonicalize: Any,
) -> tuple[list[dict[str, Any]], list[tuple[str, int]], int]:
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    occurrences: list[tuple[str, int]] = []
    family_hint_evidence_violations = 0
    source_order = 0
    for plan in plans:
        for instrument_rank, instrument in enumerate(plan.instruments):
            instrument_signals = [str(value) for value in instrument.signals]
            family_signals = [
                value
                for value in instrument_signals
                if value.startswith(FAMILY_SIGNAL_PREFIX)
            ]
            for article_rank, point in enumerate(
                instrument.entry_points[:POINTS_PER_INSTRUMENT]
            ):
                coordinate = canonicalize(
                    (str(point.unit.instrument_id), int(point.unit.node_id))
                )
                occurrences.append(coordinate)
                score = (
                    700.0
                    + float(instrument.score)
                    + float(point.score)
                    - instrument_rank * 4
                    - article_rank
                )
                point_signals = [str(value) for value in point.matched_signals]
                if family_signals and any(
                    value.startswith(FAMILY_SIGNAL_PREFIX)
                    for value in point_signals
                ):
                    family_hint_evidence_violations += 1
                existing = rows.get(coordinate)
                if existing is None:
                    existing = {
                        "doc_id": coordinate[0],
                        "node": coordinate[1],
                        "score": round(score, 6),
                        "source_order": source_order,
                        "branch_id": str(plan.branch_id),
                        "instrument_id": str(instrument.instrument_id),
                        "instrument_rank": instrument_rank,
                        "article_rank": article_rank,
                        "branch_ids": {str(plan.branch_id)},
                        "instrument_ids": {str(instrument.instrument_id)},
                        "route_signals": set(instrument_signals),
                        "matched_roles": set(
                            str(value) for value in point.matched_roles
                        ),
                        "matched_signals": set(point_signals),
                    }
                    rows[coordinate] = existing
                    source_order += 1
                else:
                    existing["branch_ids"].add(str(plan.branch_id))
                    existing["instrument_ids"].add(
                        str(instrument.instrument_id)
                    )
                    existing["route_signals"].update(instrument_signals)
                    existing["matched_roles"].update(
                        str(value) for value in point.matched_roles
                    )
                    existing["matched_signals"].update(point_signals)
                    if score > float(existing["score"]):
                        existing.update(
                            {
                                "score": round(score, 6),
                                "branch_id": str(plan.branch_id),
                                "instrument_id":
                                    str(instrument.instrument_id),
                                "instrument_rank": instrument_rank,
                                "article_rank": article_rank,
                            }
                        )
    ranked: list[dict[str, Any]] = []
    for row in rows.values():
        value = dict(row)
        for key in (
            "branch_ids",
            "instrument_ids",
            "route_signals",
            "matched_roles",
            "matched_signals",
        ):
            value[key] = sorted(value[key])
        ranked.append(value)
    ranked.sort(
        key=lambda row: (
            -float(row["score"]),
            int(row["source_order"]),
            str(row["doc_id"]),
            int(row["node"]),
            str(row["branch_id"]),
        )
    )
    return ranked, occurrences, family_hint_evidence_violations


def _instrument_receipts(plans: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "branch_id": str(plan.branch_id),
            "issue_axis": str(plan.issue_axis),
            "instruments": [
                {
                    "instrument_id": str(instrument.instrument_id),
                    "score": round(float(instrument.score), 6),
                    "signals": [str(value) for value in instrument.signals],
                    "entry_count": len(instrument.entry_points),
                }
                for instrument in plan.instruments
            ],
        }
        for plan in plans
    ]


def _execute_planner(
    planner: Any,
    index: Any,
    runtime: Any,
    case: Mapping[str, Any],
    branches: Sequence[Any],
    canonicalize: Any,
) -> dict[str, Any]:
    started = time.perf_counter()
    plans = planner.plan(str(case["question"]), case["query_plan"], branches)
    ranked, occurrences, violations = _flatten_plans(
        index, plans, canonicalize
    )
    selected = ranked[:PRESENT_CAP]
    elapsed_ms = (time.perf_counter() - started) * 1000
    instruments = _instrument_receipts(plans)
    signature_payload = {
        "plans": [plan.to_dict() for plan in plans],
        "ranked_entries": ranked,
        "selected_entries": selected,
        "occurrence_coordinates": [
            {"doc_id": doc_id, "node": node}
            for doc_id, node in occurrences
        ],
    }
    return {
        "planning_ms": round(elapsed_ms, 6),
        "signature_sha256": ledger.deterministic_sha256(signature_payload),
        "ranked_entries": ranked,
        "selected_entries": selected,
        "occurrence_coordinates": occurrences,
        "occurrence_count": len(occurrences),
        "instrument_receipts": instruments,
        "family_hint_instrument_count": sum(
            any(
                signal.startswith(FAMILY_SIGNAL_PREFIX)
                for signal in instrument["signals"]
            )
            for plan in instruments
            for instrument in plan["instruments"]
        ),
        "family_hint_evidence_violations": violations,
    }


def _coordinates(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, int]]:
    return [
        (str(row["doc_id"]), int(row["node"]))
        for row in rows
    ]


def _discard_reasons(
    before: Iterable[tuple[str, int]],
    after: Iterable[tuple[str, int]],
    reason: str,
) -> list[tuple[tuple[str, int], str]]:
    return [
        (coordinate, reason)
        for coordinate in sorted(set(before) - set(after))
    ]


def _stage_capture(
    case_id: str,
    arm_id: str,
    canonicalize: Any,
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    anchor_eligible: bool,
) -> dict[str, Any]:
    recorder = ledger.StageLedgerRecorder(case_id, arm_id, canonicalize)
    recorder.record_stage("question-source", "source", [])
    baseline_occurrences = list(baseline["occurrence_coordinates"])
    recorder.record_stage(
        "current-entry-retrieve",
        "retrieve",
        baseline_occurrences,
        parent_stage_ids=("question-source",),
    )
    if arm_id == BASELINE_ARM:
        full = baseline
        recorder.record_stage(
            "held-law-family-rerank",
            "rerank",
            baseline_occurrences,
            parent_stage_ids=("current-entry-retrieve",),
            executed=False,
            skip_reason="baseline_arm_no_held_family_rerank",
        )
    elif not anchor_eligible:
        if (
            candidate["signature_sha256"] != baseline["signature_sha256"]
            or candidate["ranked_entries"] != baseline["ranked_entries"]
        ):
            raise BoundaryError(
                f"non-anchor candidate differs from baseline: {case_id}"
            )
        full = baseline
        recorder.record_stage(
            "held-law-family-rerank",
            "rerank",
            baseline_occurrences,
            parent_stage_ids=("current-entry-retrieve",),
            executed=False,
            skip_reason="no_strong_anchor",
        )
    else:
        full = candidate
        candidate_occurrences = list(candidate["occurrence_coordinates"])
        recorder.record_stage(
            "held-law-family-rerank",
            "rerank",
            candidate_occurrences,
            parent_stage_ids=("current-entry-retrieve",),
            discard_reasons=_discard_reasons(
                baseline_occurrences,
                candidate_occurrences,
                "displaced_by_held_family_rerank_at_instrument_limit_8",
            ),
        )
    full_coordinates = _coordinates(full["ranked_entries"])
    selected_coordinates = _coordinates(full["selected_entries"])
    recorder.record_stage(
        "entry-cap-select",
        "select",
        selected_coordinates,
        parent_stage_ids=("held-law-family-rerank",),
        discard_reasons=_discard_reasons(
            full_coordinates,
            selected_coordinates,
            "outside_global_entry_cap_28",
        ),
    )
    recorder.record_stage(
        "entry-present",
        "present",
        selected_coordinates,
        parent_stage_ids=("entry-cap-select",),
    )
    capture = recorder.capture()
    ledger.validate_capture(capture, expected_stage_ids=STAGE_IDS)
    return capture


def _capture_path(case_id: str) -> Path:
    return PRODUCT_CAPTURE_DIR / f"{case_id}.json"


def _arm_record(
    result: Mapping[str, Any],
    replay: Mapping[str, Any],
    stage_capture: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "planning_ms": float(result["planning_ms"]),
        "replay_planning_ms": float(replay["planning_ms"]),
        "determinism_signature_sha256": result["signature_sha256"],
        "replay_signature_sha256": replay["signature_sha256"],
        "determinism_match":
            result["signature_sha256"] == replay["signature_sha256"],
        "candidate_count": len(result["ranked_entries"]),
        "occurrence_count": int(result["occurrence_count"]),
        "presented_count": len(result["selected_entries"]),
        "ranked_entries": deepcopy(result["ranked_entries"]),
        "presented_entries": deepcopy(result["selected_entries"]),
        "instrument_receipts": deepcopy(result["instrument_receipts"]),
        "family_hint_instrument_count":
            int(result["family_hint_instrument_count"]),
        "family_hint_evidence_violations":
            int(result["family_hint_evidence_violations"]),
        "stage_capture": deepcopy(stage_capture),
        "provider_calls": [],
        "llm_calls": [],
    }


def _validate_product_capture(
    capture: Mapping[str, Any],
    case: Mapping[str, Any],
) -> None:
    if (
        capture.get("schema_version")
        != "adr-0138-gold-free-product-capture-v1"
        or capture.get("capture_sha256")
        != _content_hash(capture, "capture_sha256")
        or capture.get("adr_id") != ADR_ID
        or capture.get("experiment_id") != EXPERIMENT_ID
        or capture.get("run_id") != RUN_ID
        or capture.get("case_id") != case.get("case_id")
        or capture.get("number") != case.get("number")
        or capture.get("suite") != case.get("suite")
        or capture.get("question_sha256") != case.get("question_sha256")
        or capture.get("query_plan_sha256") != case.get("query_plan_sha256")
        or capture.get("branches_sha256") != case.get("branches_sha256")
        or capture.get("input_lock_sha256") != _sha256(INPUT_LOCK)
        or capture.get("candidate_manifest_sha256")
        != CANDIDATE_MANIFEST_SHA256
        or capture.get("candidate_revision_id") != CANDIDATE_REVISION_ID
        or capture.get("candidate_revision_sha256")
        != CANDIDATE_REVISION_SHA256
        or capture.get("gold_visible_to_product") is not False
        or capture.get("provider_calls") != []
        or capture.get("llm_calls") != []
        or capture.get("complete") is not True
    ):
        raise BoundaryError(
            f"ADR-0138 product capture identity mismatch: {case.get('case_id')}"
        )
    _forbid_scoring_payload(capture)
    arms = capture.get("arms")
    if not isinstance(arms, Mapping) or set(arms) != set(ARMS):
        raise BoundaryError("product capture arm set mismatch")
    for arm_id in ARMS:
        arm = arms[arm_id]
        stage_capture = arm.get("stage_capture")
        if (
            arm.get("determinism_match") is not True
            or arm.get("determinism_signature_sha256")
            != arm.get("replay_signature_sha256")
            or arm.get("provider_calls") != []
            or arm.get("llm_calls") != []
            or arm.get("presented_count") > PRESENT_CAP
            or arm.get("presented_count")
            != len(arm.get("presented_entries") or ())
            or arm.get("candidate_count")
            != len(arm.get("ranked_entries") or ())
            or list(arm.get("presented_entries") or ())
            != list(arm.get("ranked_entries") or ())[:PRESENT_CAP]
            or not isinstance(stage_capture, Mapping)
            or stage_capture.get("case_id") != case.get("case_id")
            or stage_capture.get("arm_id") != arm_id
            or stage_capture.get("gold_visible_to_product") is not False
        ):
            raise BoundaryError(
                f"product capture arm contract mismatch: "
                f"{case.get('case_id')}/{arm_id}"
            )
        ledger.validate_capture(
            stage_capture, expected_stage_ids=STAGE_IDS
        )
        final = stage_capture["stages"][-1]
        if {
            (row["doc_id"], row["node"]) for row in final["after"]
        } != {
            (row["doc_id"], row["node"])
            for row in arm["presented_entries"]
        }:
            raise BoundaryError("presented rank receipt differs from ledger")
    if not capture.get("anchor_eligible"):
        if (
            arms[BASELINE_ARM]["determinism_signature_sha256"]
            != arms[CANDIDATE_ARM]["determinism_signature_sha256"]
            or arms[BASELINE_ARM]["ranked_entries"]
            != arms[CANDIDATE_ARM]["ranked_entries"]
        ):
            raise BoundaryError("non-anchor arm output mismatch")


def run_product(*, resume: bool) -> None:
    if resume:
        raise BoundaryError(
            "official run-001 cannot resume without invalidating wall latency"
        )
    started = time.perf_counter()
    _assert_source_hashes()
    input_lock = _validate_input_lock(require_manifest_hash=True)
    _validate_candidate()
    _validate_adr_pre_run(input_lock)
    if PRODUCT_SEAL.exists():
        raise BoundaryError("ADR-0138 product seal already exists")
    existing = list(PRODUCT_CAPTURE_DIR.glob("*.json"))
    if existing and not resume:
        raise BoundaryError(
            "partial product captures exist; issue a new append-only run ID"
        )

    index, runtime, preload_ms, corpus_total, live_resource = _load_runtime()
    canonicalize = ledger.index_article_root_canonicalizer(index)
    CandidatePlanner = _load_candidate_planner()
    baseline_planner = BaselinePlanner(
        runtime.atlas,
        instrument_limit=INSTRUMENT_LIMIT,
        entry_limit=ENTRY_LIMIT,
        system_map=runtime.system_map,
        semantic_card_index=runtime.semantic_cards,
    )
    candidate_planner = CandidatePlanner(
        runtime.atlas,
        instrument_limit=INSTRUMENT_LIMIT,
        entry_limit=ENTRY_LIMIT,
        system_map=runtime.system_map,
        semantic_card_index=runtime.semantic_cards,
    )
    cases = list(input_lock["cases"])

    for position, case in enumerate(cases, 1):
        case_id = str(case["case_id"])
        target = _capture_path(case_id)
        if target.exists():
            if not resume:
                raise BoundaryError(f"capture already exists: {target}")
            _validate_product_capture(_read_json(target), case)
            print(f"[resume {position}/61] {case_id}", flush=True)
            continue
        branches = branches_from_query_plan(case["query_plan"])
        explicit_anchors, closed_anchors = _strong_anchors(
            runtime, str(case["question"]), branches
        )
        anchor_eligible = bool(explicit_anchors or closed_anchors)
        planners = {
            BASELINE_ARM: baseline_planner,
            CANDIDATE_ARM: candidate_planner,
        }
        primary_order = (
            ARMS if int(case["number"]) % 2 else tuple(reversed(ARMS))
        )
        primary: dict[str, dict[str, Any]] = {}
        replay: dict[str, dict[str, Any]] = {}
        case_started = time.perf_counter()
        for arm_id in primary_order:
            primary[arm_id] = _execute_planner(
                planners[arm_id],
                index,
                runtime,
                case,
                branches,
                canonicalize,
            )
        for arm_id in reversed(primary_order):
            replay[arm_id] = _execute_planner(
                planners[arm_id],
                index,
                runtime,
                case,
                branches,
                canonicalize,
            )
            if (
                replay[arm_id]["signature_sha256"]
                != primary[arm_id]["signature_sha256"]
            ):
                raise BoundaryError(
                    f"deterministic replay mismatch: {case_id}/{arm_id}"
                )
        stages = {
            arm_id: _stage_capture(
                case_id,
                arm_id,
                canonicalize,
                primary[BASELINE_ARM],
                primary[CANDIDATE_ARM],
                anchor_eligible=anchor_eligible,
            )
            for arm_id in ARMS
        }
        capture = {
            "schema_version": "adr-0138-gold-free-product-capture-v1",
            "adr_id": ADR_ID,
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "number": int(case["number"]),
            "case_id": case_id,
            "suite": str(case["suite"]),
            "question_sha256": str(case["question_sha256"]),
            "query_plan_sha256": str(case["query_plan_sha256"]),
            "branches_sha256": str(case["branches_sha256"]),
            "input_lock_sha256": _sha256(INPUT_LOCK),
            "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
            "candidate_revision_id": CANDIDATE_REVISION_ID,
            "candidate_revision_sha256": CANDIDATE_REVISION_SHA256,
            "gold_visible_to_product": False,
            "anchor_eligible": anchor_eligible,
            "explicit_anchor_ids": explicit_anchors,
            "closed_preferred_anchor_ids": closed_anchors,
            "primary_order": list(primary_order),
            "case_wall_ms": round(
                (time.perf_counter() - case_started) * 1000, 6
            ),
            "arms": {
                arm_id: _arm_record(
                    primary[arm_id], replay[arm_id], stages[arm_id]
                )
                for arm_id in ARMS
            },
            "provider_calls": [],
            "llm_calls": [],
            "complete": True,
            "captured_at": _now(),
        }
        _attach_hash(capture, "capture_sha256")
        _validate_product_capture(capture, case)
        _write_json(target, capture, immutable=True)
        print(f"[product {position}/61] {case_id}", flush=True)

    case_by_id = {str(row["case_id"]): row for row in cases}
    receipts: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        path = _capture_path(case_id)
        capture = _read_json(path)
        _validate_product_capture(capture, case_by_id[case_id])
        receipts.append(
            {
                "number": int(capture["number"]),
                "case_id": case_id,
                "path": _relative(path),
                "file_sha256": _sha256(path),
                "capture_sha256": str(capture["capture_sha256"]),
                "complete": True,
            }
        )
    wall_ms = (time.perf_counter() - started) * 1000
    seal = {
        "schema_version": "adr-0138-product-capture-seal-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "case_count": len(receipts),
        "gold_visible_to_product": False,
        "input_lock_path": _relative(INPUT_LOCK),
        "input_lock_sha256": _sha256(INPUT_LOCK),
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "candidate_revision_id": CANDIDATE_REVISION_ID,
        "candidate_revision_sha256": CANDIDATE_REVISION_SHA256,
        "resource_admission": deepcopy(live_resource),
        "corpus_article_roots": corpus_total,
        "preload_ms": preload_ms,
        "run_product_wall_ms": round(wall_ms, 6),
        "provider_calls": 0,
        "llm_calls": 0,
        "case_receipts": receipts,
        "sealed_at": _now(),
    }
    _attach_hash(seal, "seal_sha256")
    _write_json(PRODUCT_SEAL, seal, immutable=True)
    print(
        json.dumps(
            {
                "product_seal": _relative(PRODUCT_SEAL),
                "file_sha256": _sha256(PRODUCT_SEAL),
                "content_sha256": seal["seal_sha256"],
                "cases": len(receipts),
                "run_product_wall_ms": round(wall_ms, 6),
                "provider_calls": 0,
                "llm_calls": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _validate_product_seal(
    input_lock: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    seal = _read_json(PRODUCT_SEAL)
    if (
        seal.get("schema_version") != "adr-0138-product-capture-seal-v1"
        or seal.get("seal_sha256") != _content_hash(seal, "seal_sha256")
        or seal.get("adr_id") != ADR_ID
        or seal.get("experiment_id") != EXPERIMENT_ID
        or seal.get("run_id") != RUN_ID
        or seal.get("case_count") != len(CASE_IDS)
        or seal.get("gold_visible_to_product") is not False
        or seal.get("input_lock_sha256") != _sha256(INPUT_LOCK)
        or seal.get("candidate_manifest_sha256")
        != CANDIDATE_MANIFEST_SHA256
        or seal.get("candidate_revision_id") != CANDIDATE_REVISION_ID
        or seal.get("candidate_revision_sha256")
        != CANDIDATE_REVISION_SHA256
        or seal.get("provider_calls") != 0
        or seal.get("llm_calls") != 0
        or seal.get("resource_admission")
        != input_lock.get("resource_admission")
    ):
        raise BoundaryError("ADR-0138 product seal identity mismatch")
    receipts = list(seal.get("case_receipts") or ())
    if [row.get("case_id") for row in receipts] != list(CASE_IDS):
        raise BoundaryError("ADR-0138 product seal case order mismatch")
    case_by_id = {
        str(row["case_id"]): row for row in input_lock["cases"]
    }
    captures: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        case_id = str(receipt["case_id"])
        path = _repo_path(str(receipt["path"]))
        _assert_file_hash(
            path, str(receipt["file_sha256"]), f"ADR-0138 capture {case_id}"
        )
        capture = _read_json(path)
        _validate_product_capture(capture, case_by_id[case_id])
        if (
            capture.get("capture_sha256") != receipt.get("capture_sha256")
            or receipt.get("complete") is not True
        ):
            raise BoundaryError(f"ADR-0138 receipt mismatch: {case_id}")
        captures[case_id] = capture
    return seal, captures


def _final_coordinates(graded: Mapping[str, Any]) -> set[tuple[str, int]]:
    return {
        (str(row["doc_id"]), int(row["node"]))
        for row in graded["stages"][-1]["after"]
    }


def _score_coordinates(
    rows: Iterable[Mapping[str, Any]],
    canonicalize: Any,
) -> set[tuple[str, int]]:
    values: set[tuple[str, int]] = set()
    for row in rows:
        doc_id, node = row.get("doc_id"), row.get("node")
        if doc_id and isinstance(node, int) and not isinstance(node, bool):
            values.add(canonicalize((str(doc_id), int(node))))
    return values


def _paired_counts(
    baseline: set[tuple[str, int]],
    candidate: set[tuple[str, int]],
    targets: set[tuple[str, int]],
) -> dict[str, int]:
    counts = {
        "candidate_only": 0,
        "baseline_only": 0,
        "both_hit": 0,
        "both_miss": 0,
    }
    for coordinate in targets:
        baseline_hit = coordinate in baseline
        candidate_hit = coordinate in candidate
        key = (
            "candidate_only"
            if candidate_hit and not baseline_hit
            else "baseline_only"
            if baseline_hit and not candidate_hit
            else "both_hit"
            if baseline_hit and candidate_hit
            else "both_miss"
        )
        counts[key] += 1
    return counts


def _sum_counts(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def _arm_summary(
    arm_id: str,
    rows: Sequence[Mapping[str, Any]],
    captures: Mapping[str, Mapping[str, Any]],
    corpus_total: int,
) -> dict[str, Any]:
    presented = [int(row["arms"][arm_id]["presented_count"]) for row in rows]
    planning = [
        float(captures[str(row["case_id"])]["arms"][arm_id]["planning_ms"])
        for row in rows
    ]
    decisive_total = sum(int(row["decisive_total"]) for row in rows)
    decisive_hits = sum(int(row["arms"][arm_id]["decisive_hits"]) for row in rows)
    companion_total = sum(int(row["companion_total"]) for row in rows)
    companion_hits = sum(int(row["arms"][arm_id]["companion_hits"]) for row in rows)
    family_stage = [
        capture["arms"][arm_id]["stage_capture"]["stages"][2]
        for capture in captures.values()
    ]
    cap_stage = [
        capture["arms"][arm_id]["stage_capture"]["stages"][3]
        for capture in captures.values()
    ]
    return {
        "decisive_hits": decisive_hits,
        "decisive_total": decisive_total,
        "decisive_recall":
            round(decisive_hits / decisive_total, 6) if decisive_total else 0.0,
        "all_required_cases": sum(
            bool(row["arms"][arm_id]["all_decisive_present"]) for row in rows
        ),
        "all_required_total": len(rows),
        "companion_hits": companion_hits,
        "companion_total": companion_total,
        "companion_recall":
            round(companion_hits / companion_total, 6)
            if companion_total
            else 0.0,
        "presented_total": sum(presented),
        "presented_mean":
            round(statistics.mean(presented), 6) if presented else 0.0,
        "presented_p50":
            round(statistics.median(presented), 6) if presented else 0.0,
        "presented_p95": _percentile(presented, 0.95),
        "presented_max": max(presented) if presented else 0,
        "selectivity":
            round(statistics.mean(presented) / corpus_total, 10)
            if presented and corpus_total
            else 0.0,
        "planning_ms_p50": _percentile(planning, 0.50),
        "planning_ms_p95": _percentile(planning, 0.95),
        "planning_ms_max": round(max(planning), 6) if planning else 0.0,
        "family_stage_added": sum(
            int(stage["added_count"]) for stage in family_stage
        ),
        "family_stage_discarded": sum(
            int(stage["discarded_count"]) for stage in family_stage
        ),
        "cap_stage_discarded": sum(
            int(stage["discarded_count"]) for stage in cap_stage
        ),
        "deterministic_cases": sum(
            bool(captures[str(row["case_id"])]["arms"][arm_id][
                "determinism_match"
            ])
            for row in rows
        ),
        "provider_calls": 0,
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }


def _question_document(
    input_case: Mapping[str, Any],
    scoring_case: Mapping[str, Any],
    row: Mapping[str, Any],
    graded_by_arm: Mapping[str, Mapping[str, Any]],
) -> str:
    lines = [
        f"# ADR-0138 질문 {int(input_case['number']):03d} — "
        f"{input_case['case_id']}",
        "",
        "## 1. 실행 메타",
        "",
        f"- run: {RUN_ID}",
        f"- case: {input_case['case_id']}",
        f"- suite: {input_case['suite']}",
        "- product/provider/LLM calls: 0",
        "- accounting unit: case_id + canonical article-root coordinate",
        "",
        "## 2. 사용자 질문 원문",
        "",
        str(input_case["question"]),
        "",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개",
        "",
        str(scoring_case.get("reference_answer") or ""),
        "",
        "정답 조문 좌표는 ADR-0138 product seal 검증 뒤 exact set "
        "containment 채점에만 사용했다.",
        "",
        "## 4. 제품 입력을 구성한 원값",
        "",
        f"- query plan source: {QUERY_PLAN_POINTER}",
        f"- query plan SHA-256: {input_case['query_plan_sha256']}",
        f"- branches SHA-256: {input_case['branches_sha256']}",
        f"- explicit anchor IDs: "
        f"{json.dumps(row['explicit_anchor_ids'], ensure_ascii=False)}",
        f"- closed preferred anchor IDs: "
        f"{json.dumps(row['closed_preferred_anchor_ids'], ensure_ascii=False)}",
        "",
        "Frozen query plan (canonical JSON):",
        "",
        json.dumps(
            input_case["query_plan"],
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ),
        "",
        "### 회수·탈락 단계 원장 — run·arm별",
        "",
        "| arm | stage | executed | before→after | added/discarded | "
        "gold before→after |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for arm_id in ARMS:
        for stage in graded_by_arm[arm_id]["stages"]:
            lines.append(
                f"| {arm_id} | {stage['stage_id']} | "
                f"{str(stage['executed']).lower()} | "
                f"{stage['before_count']}→{stage['after_count']} | "
                f"+{stage['added_count']}/-{stage['discarded_count']} | "
                f"{stage['gold_before']}→{stage['gold_after']} |"
            )
    lines.extend(
        [
            "",
            f"- dedicated ledger artifact: `{_relative(LEDGER_ARTIFACT)}`",
            f"- raw product capture: "
            f"`{_relative(_capture_path(str(input_case['case_id'])))}`",
            f"- raw product capture SHA-256: "
            f"`{_sha256(_capture_path(str(input_case['case_id'])))}`",
            "",
            "### 단계별 exact 좌표·탈락 사유·gold 손실",
            "",
        ]
    )
    for arm_id in ARMS:
        graded = graded_by_arm[arm_id]
        metadata = {
            key: deepcopy(graded[key])
            for key in (
                "gold_total",
                "gold_identities",
                "gold_sha256",
                "ledger_sha256",
            )
        }
        lines.extend(
            [
                f"#### {arm_id} graded ledger metadata",
                "",
                "```json",
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
                "```",
                "",
            ]
        )
        for stage in graded["stages"]:
            lines.extend(
                [
                    f"##### {arm_id} / {stage['stage_id']}",
                    "",
                    "```json",
                    json.dumps(
                        stage,
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                    ),
                    "```",
                    "",
                ]
            )
    lines.extend(
        [
            "",
            "## 5. 제품 모델 호출 — run·arm별 실제 원문",
            "",
            "해당 없음. 두 arm 모두 frozen query plan을 쓰는 결정론적 "
            "planner이며 제품 모델 호출은 0회다.",
            "",
            "## 6. 중간 LLM 호출 — router/compiler/verifier/repair",
            "",
            "해당 없음. router/compiler/verifier/repair 호출은 0회다.",
            "",
            "## 7. 채점 호출과 반복 판정",
            "",
            "LLM judge 호출은 0회다. ADR-0138 product seal 이후 decisive "
            "및 companion canonical 좌표를 exact containment로 1회 채점했다.",
            "",
            "## 8. 사례 최종 판정",
            "",
            "| arm | decisive | all decisive | companion | presented |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for arm_id in ARMS:
        arm = row["arms"][arm_id]
        lines.append(
            f"| {arm_id} | {arm['decisive_hits']}/"
            f"{row['decisive_total']} | "
            f"{str(arm['all_decisive_present']).lower()} | "
            f"{arm['companion_hits']}/{row['companion_total']} | "
            f"{arm['presented_count']} |"
        )
    for arm_id in ARMS:
        lines.extend(
            [
                "",
                f"### {arm_id} exact final outcome",
                "",
                "```json",
                json.dumps(
                    row["arms"][arm_id],
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "",
            f"- paired all-required outcome: {row['paired_case_outcome']}",
            f"- failure type: {row['failure_type']}",
            "",
        ]
    )
    return "\n".join(lines)


def score() -> None:
    final_outputs = (LEDGER_ARTIFACT, RUN_ARTIFACT, QUESTION_INDEX)
    existing_outputs = [path for path in final_outputs if path.exists()]
    existing_outputs.extend(
        sorted((ADR / "실험").glob("질문-*.md"))
    )
    if existing_outputs:
        raise BoundaryError(
            "score artifacts are append-only; existing: "
            + ", ".join(_relative(path) for path in existing_outputs)
        )
    score_started = time.perf_counter()
    _assert_source_hashes()
    input_lock = _validate_input_lock(require_manifest_hash=True)
    _validate_candidate()
    _validate_adr_pre_run(input_lock)

    # This validation completes before the first scoring-fixture read.
    product_seal, captures = _validate_product_seal(input_lock)
    product_seal_validated_at = _now()

    _assert_file_hash(
        SCORING_FIXTURE, SCORING_SHA256, "ADR-0114 scoring fixture"
    )
    scoring = _read_json(SCORING_FIXTURE)
    gold_opened_at = _now()
    if (
        scoring.get("schema_version")
        != "adr-0114-offline-scoring-fixture-v1"
        or scoring.get("product_access")
        != "forbidden-before-valid-product-seal"
    ):
        raise BoundaryError("scoring fixture schema/boundary mismatch")
    scoring_cases = list(scoring.get("cases") or ())
    if [row.get("case_id") for row in scoring_cases] != list(CASE_IDS):
        raise BoundaryError("scoring fixture case order mismatch")
    scoring_by_id = {
        str(row["case_id"]): row for row in scoring_cases
    }

    index, runtime, score_preload_ms, corpus_total, live_resource = (
        _load_runtime()
    )
    if live_resource != product_seal.get("resource_admission"):
        raise BoundaryError("score runtime differs from sealed product runtime")
    canonicalize = ledger.index_article_root_canonicalizer(index)
    input_by_id = {
        str(row["case_id"]): row for row in input_lock["cases"]
    }
    graded_ledgers: list[dict[str, Any]] = []
    graded_by_case: dict[str, dict[str, dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    decisive_paired = {
        "candidate_only": 0,
        "baseline_only": 0,
        "both_hit": 0,
        "both_miss": 0,
    }
    companion_paired = dict(decisive_paired)
    case_paired = {
        "candidate_only": 0,
        "baseline_only": 0,
        "both_pass": 0,
        "both_fail": 0,
    }

    for case_id in CASE_IDS:
        capture = captures[case_id]
        score_case = scoring_by_id[case_id]
        decisive = _score_coordinates(
            score_case.get("gold_articles") or (), canonicalize
        )
        companions = _score_coordinates(
            score_case.get("required_companions") or (), canonicalize
        )
        if not decisive:
            raise BoundaryError(f"case has no decisive coordinates: {case_id}")
        graded_by_arm: dict[str, dict[str, Any]] = {}
        final_by_arm: dict[str, set[tuple[str, int]]] = {}
        arm_rows: dict[str, dict[str, Any]] = {}
        for arm_id in ARMS:
            graded = ledger.grade_capture(
                capture["arms"][arm_id]["stage_capture"],
                decisive,
                canonicalizer=ledger.identity_canonicalizer,
            )
            ledger.validate_graded_ledger(
                graded, expected_stage_ids=STAGE_IDS
            )
            graded_ledgers.append(graded)
            graded_by_arm[arm_id] = graded
            final = _final_coordinates(graded)
            final_by_arm[arm_id] = final
            arm_rows[arm_id] = {
                "decisive_hits": len(final & decisive),
                "all_decisive_present": decisive <= final,
                "companion_hits": len(final & companions),
                "all_companions_present": companions <= final,
                "presented_count": len(final),
                "missing_decisive": [
                    {"doc_id": doc_id, "node": node}
                    for doc_id, node in sorted(decisive - final)
                ],
                "missing_companions": [
                    {"doc_id": doc_id, "node": node}
                    for doc_id, node in sorted(companions - final)
                ],
            }
        _sum_counts(
            decisive_paired,
            _paired_counts(
                final_by_arm[BASELINE_ARM],
                final_by_arm[CANDIDATE_ARM],
                decisive,
            ),
        )
        _sum_counts(
            companion_paired,
            _paired_counts(
                final_by_arm[BASELINE_ARM],
                final_by_arm[CANDIDATE_ARM],
                companions,
            ),
        )
        baseline_pass = bool(
            arm_rows[BASELINE_ARM]["all_decisive_present"]
        )
        candidate_pass = bool(
            arm_rows[CANDIDATE_ARM]["all_decisive_present"]
        )
        paired_case_outcome = (
            "candidate_only"
            if candidate_pass and not baseline_pass
            else "baseline_only"
            if baseline_pass and not candidate_pass
            else "both_pass"
            if baseline_pass and candidate_pass
            else "both_fail"
        )
        case_paired[paired_case_outcome] += 1
        failure_type = (
            "none"
            if candidate_pass
            else "retrieval_miss"
        )
        row = {
            "number": int(input_by_id[case_id]["number"]),
            "case_id": case_id,
            "suite": str(input_by_id[case_id]["suite"]),
            "anchor_eligible": bool(capture["anchor_eligible"]),
            "explicit_anchor_ids": deepcopy(capture["explicit_anchor_ids"]),
            "closed_preferred_anchor_ids":
                deepcopy(capture["closed_preferred_anchor_ids"]),
            "decisive_total": len(decisive),
            "companion_total": len(companions),
            "arms": arm_rows,
            "paired_case_outcome": paired_case_outcome,
            "failure_type": failure_type,
        }
        rows.append(row)
        graded_by_case[case_id] = graded_by_arm

    decisive_total = sum(int(row["decisive_total"]) for row in rows)
    companion_total = sum(int(row["companion_total"]) for row in rows)
    if (
        decisive_total != 90
        or companion_total != 22
        or sum(decisive_paired.values()) != decisive_total
        or sum(companion_paired.values()) != companion_total
        or sum(case_paired.values()) != len(CASE_IDS)
    ):
        raise BoundaryError(
            "canonical scoring totals or paired partitions differ from "
            "the frozen 90 decisive / 22 companion / 61 case contract"
        )

    declared = {arm_id: STAGE_IDS for arm_id in ARMS}
    ledger_run = ledger.build_run_artifact(
        RUN_ID, graded_ledgers, declared
    )
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [ledger_run]
    )
    ledger.validate_experiment_artifact(experiment_ledger)
    _write_json(LEDGER_ARTIFACT, experiment_ledger)

    by_arm = {
        arm_id: _arm_summary(
            arm_id, rows, captures, corpus_total
        )
        for arm_id in ARMS
    }
    deltas = [
        float(captures[case_id]["arms"][CANDIDATE_ARM]["planning_ms"])
        - float(captures[case_id]["arms"][BASELINE_ARM]["planning_ms"])
        for case_id in CASE_IDS
    ]
    non_anchor_cases = [
        case_id for case_id in CASE_IDS
        if not captures[case_id]["anchor_eligible"]
    ]
    non_anchor_exact = sum(
        captures[case_id]["arms"][BASELINE_ARM]["ranked_entries"]
        == captures[case_id]["arms"][CANDIDATE_ARM]["ranked_entries"]
        for case_id in non_anchor_cases
    )
    family_hint_violations = sum(
        int(captures[case_id]["arms"][CANDIDATE_ARM][
            "family_hint_evidence_violations"
        ])
        for case_id in CASE_IDS
    )
    criteria = {
        "all_61_cases_complete": len(rows) == 61,
        "all_122_stage_ledgers_valid": len(graded_ledgers) == 122,
        "deterministic_replay_61_by_2": all(
            captures[case_id]["arms"][arm_id]["determinism_match"]
            for case_id in CASE_IDS
            for arm_id in ARMS
        ),
        "candidate_decisive_gain_at_least_one":
            by_arm[CANDIDATE_ARM]["decisive_hits"]
            >= by_arm[BASELINE_ARM]["decisive_hits"] + 1,
        "baseline_only_decisive_zero":
            decisive_paired["baseline_only"] == 0,
        "all_required_cases_noninferior":
            by_arm[CANDIDATE_ARM]["all_required_cases"]
            >= by_arm[BASELINE_ARM]["all_required_cases"],
        "companion_hits_noninferior":
            by_arm[CANDIDATE_ARM]["companion_hits"]
            >= by_arm[BASELINE_ARM]["companion_hits"],
        "baseline_only_companion_zero":
            companion_paired["baseline_only"] == 0,
        "present_cap_28_respected":
            max(by_arm[arm_id]["presented_max"] for arm_id in ARMS)
            <= PRESENT_CAP,
        "candidate_planning_p95_within_500_ms":
            by_arm[CANDIDATE_ARM]["planning_ms_p95"] <= 500.0,
        "planning_delta_p95_within_50_ms":
            _percentile(deltas, 0.95) <= 50.0,
        "run_product_wall_with_preload_within_180_s":
            float(product_seal["run_product_wall_ms"]) <= 180_000.0,
        "provider_llm_judge_calls_zero":
            product_seal["provider_calls"] == 0
            and product_seal["llm_calls"] == 0,
        "family_hint_evidence_coverage_violations_zero":
            family_hint_violations == 0,
        "non_anchor_output_exact":
            non_anchor_exact == len(non_anchor_cases),
        "closed_preferred_anchor_coverage_zero_recorded":
            sum(
                len(captures[case_id]["closed_preferred_anchor_ids"])
                for case_id in CASE_IDS
            )
            == 0,
        "product_source_hashes_unchanged": all(
            _sha256(_repo_path(raw)) == expected
            for raw, expected in SOURCE_HASHES.items()
        ),
    }
    criteria["all_frozen_criteria_met"] = all(criteria.values())

    for row in rows:
        case_id = str(row["case_id"])
        question_path = (
            ADR
            / "실험"
            / f"질문-{int(row['number']):03d}-{case_id}.md"
        )
        _write_text(
            question_path,
            _question_document(
                input_by_id[case_id],
                scoring_by_id[case_id],
                row,
                graded_by_case[case_id],
            ),
        )
    question_entries = [
        {
            "number": int(row["number"]),
            "case_id": str(row["case_id"]),
            "file": f"질문-{int(row['number']):03d}-{row['case_id']}.md",
            "sha256": _sha256(
                ADR
                / "실험"
                / f"질문-{int(row['number']):03d}-{row['case_id']}.md"
            ),
        }
        for row in rows
    ]
    question_index = {
        "schema_version": "adr-0138-question-index-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "questions": question_entries,
    }
    _attach_hash(question_index, "artifact_sha256")
    _write_json(QUESTION_INDEX, question_index)

    run_value = {
        "schema_version": "adr-0138-law-family-entry-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "completed_at": _now(),
        "gold_boundary": {
            "adr_0138_product_seal_validated_at":
                product_seal_validated_at,
            "scoring_fixture_opened_at": gold_opened_at,
            "gold_opened_after_product_seal": True,
            "gold_visible_to_product": False,
        },
        "source": {
            "input_lock_path": _relative(INPUT_LOCK),
            "input_lock_sha256": _sha256(INPUT_LOCK),
            "product_seal_path": _relative(PRODUCT_SEAL),
            "product_seal_sha256": _sha256(PRODUCT_SEAL),
            "product_seal_content_sha256": product_seal["seal_sha256"],
            "scoring_fixture_path": _relative(SCORING_FIXTURE),
            "scoring_fixture_sha256": SCORING_SHA256,
            "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
            "candidate_revision_id": CANDIDATE_REVISION_ID,
            "candidate_revision_sha256": CANDIDATE_REVISION_SHA256,
            "ledger_path": _relative(LEDGER_ARTIFACT),
            "ledger_sha256": _sha256(LEDGER_ARTIFACT),
            "ledger_content_sha256": experiment_ledger["artifact_sha256"],
            "question_index_path": _relative(QUESTION_INDEX),
            "question_index_sha256": _sha256(QUESTION_INDEX),
        },
        "configuration": {
            "instrument_limit": INSTRUMENT_LIMIT,
            "entry_limit": ENTRY_LIMIT,
            "points_per_instrument": POINTS_PER_INSTRUMENT,
            "present_cap": PRESENT_CAP,
            "score_formula": (
                "700 + instrument.score + point.score "
                "- 4*instrument_rank - article_rank"
            ),
            "closed_preferred_anchor_tested": False,
        },
        "summary": {
            "cases": len(rows),
            "decisive_total": sum(row["decisive_total"] for row in rows),
            "companion_total": sum(row["companion_total"] for row in rows),
            "corpus_article_roots": corpus_total,
            "by_arm": by_arm,
            "decisive_coordinate_paired": decisive_paired,
            "companion_coordinate_paired": companion_paired,
            "all_required_case_paired": case_paired,
            "anchor_eligible_cases": sum(
                bool(captures[case_id]["anchor_eligible"])
                for case_id in CASE_IDS
            ),
            "non_anchor_cases": len(non_anchor_cases),
            "non_anchor_exact_cases": non_anchor_exact,
            "closed_preferred_anchor_occurrences": 0,
            "planning_delta_ms_p95": _percentile(deltas, 0.95),
            "family_hint_evidence_violations": family_hint_violations,
            "run_product_wall_ms":
                float(product_seal["run_product_wall_ms"]),
            "run_product_preload_ms":
                float(product_seal["preload_ms"]),
            "score_preload_ms": score_preload_ms,
            "score_wall_ms": round(
                (time.perf_counter() - score_started) * 1000, 6
            ),
        },
        "frozen_criteria_measurement": criteria,
        "usage": {
            "provider_calls": 0,
            "llm_calls": 0,
            "judge_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        },
        "rows": rows,
    }
    _attach_hash(run_value, "artifact_sha256")
    _write_json(RUN_ARTIFACT, run_value)
    print(
        json.dumps(
            {
                "run_artifact": _relative(RUN_ARTIFACT),
                "file_sha256": _sha256(RUN_ARTIFACT),
                "content_sha256": run_value["artifact_sha256"],
                "ledger_sha256": _sha256(LEDGER_ARTIFACT),
                "all_frozen_criteria_met":
                    criteria["all_frozen_criteria_met"],
                "baseline_decisive":
                    by_arm[BASELINE_ARM]["decisive_hits"],
                "candidate_decisive":
                    by_arm[CANDIDATE_ARM]["decisive_hits"],
                "provider_calls": 0,
                "llm_calls": 0,
                "judge_calls": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "freeze-input",
        help="derive the gold-free ADR-0138 input lock",
    )
    subcommands.add_parser(
        "preflight",
        help="validate frozen data/code/runner hashes without retrieval",
    )
    product = subcommands.add_parser(
        "run-product",
        help="run and seal both gold-free deterministic planner arms",
    )
    product.add_argument(
        "--resume",
        action="store_true",
        help="refused for official append-only run-001; issue a new run ID",
    )
    subcommands.add_parser(
        "score",
        help="validate ADR-0138 product seal, then open gold and score",
    )
    args = parser.parse_args()
    if args.command == "freeze-input":
        freeze_input()
    elif args.command == "preflight":
        preflight()
    elif args.command == "run-product":
        run_product(resume=bool(args.resume))
    elif args.command == "score":
        score()
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
