#!/usr/bin/env python3
"""ADR-0126 internal-rule data audit, golden split, and ADR-0114 retrieval probe."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag import article_reachability  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legalclosure_runtime  # noqa: E402
from lawrag.core.rag import scopes as scopes_mod  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0126"
EXPERIMENT_ID = "ADR-0126-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "integrated-seven-layer-internal"
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
MODEL = "claude-haiku-4-5-20251001"
ADR = ROOT / "docs/adr/ADR-0126-internal-rule-adr0114-retrieval-golden"
GOLDEN = ROOT / "data/review/internal_rule_retrieval_v1.json"
PUBLIC = ADR / "artifacts/public-questions-run-001.json"
SCORING = ADR / "artifacts/scoring-fixture-run-001.json"
AUDIT = ADR / "artifacts/internal-data-audit.json"
CAPTURES = ADR / "artifacts/product-captures/run-001"
SEAL = ADR / "artifacts/product-capture-seal-run-001.json"
LEDGER = ADR / "artifacts/retrieval-stage-ledger-run-001.json"
RUN = ADR / "artifacts/run-001.json"
MANIFEST = ADR / "실험/manifest.json"
INTERNAL_DOC_IDS = (
    "38803e534c832e19",
    "3bad39ac4c01eec6",
    "a87d28a238399591",
)
CURRENT_INTERNAL_DOC_IDS = (
    "3bad39ac4c01eec6",
    "a87d28a238399591",
)
REQUEST_DOC_ID = "ea6809e5776be26e"
EXPECTED_CASE_IDS = tuple(f"internal-{number:03d}" for number in range(1, 13))


class BoundaryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=ledger.canonical_json)
    try:
        return _jsonable(asdict(value))
    except (TypeError, ValueError):
        return str(value)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _percentile(values: Iterable[float], ratio: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    return rows[min(len(rows) - 1, round((len(rows) - 1) * ratio))]


def _legacy_runner():
    path = ROOT / "scripts/rag_integrated_legal_research_golden_61.py"
    spec = importlib.util.spec_from_file_location("adr0114_runner_for_adr0126", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ADR-0114 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = _read_json(MANIFEST)
    raw_plans = manifest["design"]["retrieval_stage_plan"]["stages_by_arm"]
    module.BASELINE_ARM = BASELINE_ARM
    module.CANDIDATE_ARM = CANDIDATE_ARM
    module.ARMS = ARMS
    module.ADR_ID = ADR_ID
    module.EXPERIMENT_ID = EXPERIMENT_ID
    module.RUN_ID = RUN_ID
    module.MODEL = MODEL
    module.STAGE_PLAN = {
        arm: tuple({
            "stage_id": str(row["stage_id"]),
            "kind": str(row["kind"]),
            "parent_stage_ids": tuple(row.get("parent_stage_ids") or ()),
        } for row in raw_plans[arm])
        for arm in ARMS
    }
    return module


def _article_rows(view: Any) -> list[dict[str, Any]]:
    return [node for node in view.nodes if node.get("family") == "kr_article"]


def _body_article_rows(view: Any) -> list[dict[str, Any]]:
    return [node for node in _article_rows(view) if view.coordinate_scope(node["id"]) == "body"]


def _graph_counts(doc_ids: Sequence[str]) -> dict[str, dict[str, int]]:
    current = _read_json(ROOT / "data/legal_graph/CURRENT.json")
    generation = ROOT / "data/legal_graph/generations" / str(current["generation_id"])
    files = (
        "canonical/structural_units.jsonl.gz",
        "projections/provision_cards.jsonl.gz",
        "projections/semantic_cards.jsonl.gz",
        "canonical/legal_entities.jsonl.gz",
        "canonical/rule_assertions.jsonl.gz",
        "canonical/relation_assertions.jsonl.gz",
        "canonical/legacy_assertions.jsonl.gz",
    )
    out: dict[str, dict[str, int]] = {}
    for relative in files:
        counts = {doc_id: 0 for doc_id in doc_ids}
        with gzip.open(generation / relative, "rt", encoding="utf-8") as handle:
            for line in handle:
                for doc_id in doc_ids:
                    if doc_id in line:
                        counts[doc_id] += 1
        out[relative] = counts
    return out


def audit_internal_data() -> dict[str, Any]:
    golden = _read_json(GOLDEN)
    index = index_mod.current()
    resolved = scopes_mod.resolve(index, "내규")
    if resolved is None:
        raise BoundaryError("built-in internal scope is missing")

    source_checks = []
    for source in golden["source_documents"]:
        doc_id = str(source["doc_id"])
        body = ROOT / "data/corpus/internal" / f"{source['name']}.docx"
        structure = ROOT / "data/structure" / doc_id / "result.json"
        source_checks.append({
            "doc_id": doc_id,
            "body_path": str(body.relative_to(ROOT)),
            "body_sha256": _sha256(body),
            "body_hash_match": _sha256(body) == source["body_sha256"],
            "structure_path": str(structure.relative_to(ROOT)),
            "structure_sha256": _sha256(structure),
            "structure_hash_match": _sha256(structure) == source["structure_sha256"],
        })

    documents = []
    all_rule_articles = current_articles = current_body_articles = 0
    for doc_id in (*INTERNAL_DOC_IDS, REQUEST_DOC_ID):
        view = index.docs[doc_id]
        articles = _article_rows(view)
        body_articles = _body_article_rows(view)
        if doc_id in INTERNAL_DOC_IDS:
            all_rule_articles += len(articles)
        if doc_id in CURRENT_INTERNAL_DOC_IDS:
            current_articles += len(articles)
            current_body_articles += len(body_articles)
        result = _read_json(ROOT / "data/structure" / doc_id / "result.json")
        render_dir = ADR / "artifacts/docx-render"
        rendered_pages = len(list(render_dir.glob(f"{view.name}-page-*.png")))
        documents.append({
            "doc_id": doc_id,
            "name": view.name,
            "kind": view.kind,
            "scope_kind": view.scope_kind,
            "status": view.status,
            "is_current": bool(view.is_current),
            "nodes": len(view.nodes),
            "article_roots": len(articles),
            "body_article_roots": len(body_articles),
            "structure_pages": len(result.get("pages") or ()),
            "word_rendered_pages": rendered_pages,
            "page_model_differs": rendered_pages != len(result.get("pages") or ()),
            "fitness": deepcopy(result.get("fitness") or {}),
            "warnings": list(result.get("warnings") or ()),
        })

    coordinate_checks = []
    for case in golden["cases"]:
        for expected in case["expected_articles"]:
            doc_id, node_id = str(expected["doc_id"]), int(expected["node"])
            view = index.docs.get(doc_id)
            node = view.by_id.get(node_id) if view is not None else None
            text = view.section_text(node) if node is not None else ""
            quote = str(expected["source_quote"])
            coordinate_checks.append({
                "case_id": case["case_id"],
                "doc_id": doc_id,
                "node": node_id,
                "path": view.path(node_id) if node is not None else "",
                "article_root_exists": bool(node and node.get("family") == "kr_article"),
                "source_quote": quote,
                "quote_in_structure": quote in text,
            })

    guideline_links = [
        row for row in index.cross_from("a87d28a238399591")
        if int(row.get("src") or -1) == 33 and str(row.get("surface") or "") == "제12조"
    ]
    link_targets_current = bool(guideline_links) and all(
        row.get("dst_doc") == "3bad39ac4c01eec6" for row in guideline_links
    )
    structure_gate = (
        all(row["body_hash_match"] and row["structure_hash_match"] for row in source_checks)
        and all(row["article_root_exists"] and row["quote_in_structure"] for row in coordinate_checks)
        and all_rule_articles == 53
        and current_articles == 34
        and current_body_articles == 30
        and set(resolved.doc_ids) == set(CURRENT_INTERNAL_DOC_IDS)
    )
    receipt = {
        "schema_version": "adr-0126-internal-data-audit-v1",
        "adr_id": ADR_ID,
        "audit_as_of": str(golden["as_of"]),
        "source_checks": source_checks,
        "documents": documents,
        "counts": {
            "all_internal_rule_article_roots": all_rule_articles,
            "current_internal_article_roots": current_articles,
            "current_internal_body_article_roots": current_body_articles,
            "gold_cases": len(golden["cases"]),
            "gold_coordinates": len(coordinate_checks),
        },
        "internal_scope": {
            "doc_ids": sorted(resolved.doc_ids),
            "expected_doc_ids": sorted(CURRENT_INTERNAL_DOC_IDS),
            "exact": set(resolved.doc_ids) == set(CURRENT_INTERNAL_DOC_IDS),
        },
        "gold_coordinate_checks": coordinate_checks,
        "graph_rows": _graph_counts((*INTERNAL_DOC_IDS, REQUEST_DOC_ID)),
        "known_defects": {
            "review_request_scope_kind": index.docs[REQUEST_DOC_ID].scope_kind,
            "review_request_expected_scope_kind": "질의재료(검색 권위 아님)",
            "review_request_classification_ok": False,
            "guideline_article_10_cross_links": guideline_links,
            "guideline_article_10_targets_current_v2": link_targets_current,
        },
        "structure_gate_passed": structure_gate,
        "retrieval_probe_usable": structure_gate,
        "status": "usable_with_known_link_and_classification_defects" if structure_gate else "blocked_by_data",
    }
    receipt["audit_sha256"] = ledger.deterministic_sha256(receipt)
    _write_json(AUDIT, receipt)
    return receipt


def prepare_fixtures() -> dict[str, Any]:
    audit = audit_internal_data()
    if not audit["retrieval_probe_usable"]:
        raise BoundaryError("internal data structure gate failed")
    golden = _read_json(GOLDEN)
    cases = list(golden.get("cases") or ())
    if [row.get("case_id") for row in cases] != list(EXPECTED_CASE_IDS):
        raise BoundaryError("golden case order differs from frozen 12-case plan")
    public = {
        "schema_version": "adr-0126-public-questions-v1",
        "dataset_id": golden["dataset_id"],
        "gold_visible_to_product": False,
        "selection_rule": golden["selection_rule"],
        "cases": [{
            "number": int(case["number"]),
            "case_id": str(case["case_id"]),
            "suite": str(case["suite"]),
            "question": str(case["question"]),
            "material": case.get("material"),
        } for case in cases],
    }
    scoring = {
        "schema_version": "adr-0126-offline-scoring-v1",
        "dataset_id": golden["dataset_id"],
        "product_access": "forbidden-before-valid-product-seal",
        "forbidden_final_documents": deepcopy(golden["forbidden_final_documents"]),
        "cases": [{
            "number": int(case["number"]),
            "case_id": str(case["case_id"]),
            "expected_articles": deepcopy(case["expected_articles"]),
        } for case in cases],
    }
    _write_json(PUBLIC, public)
    _write_json(SCORING, scoring)
    receipt = {
        "status": "prepared",
        "cases": len(cases),
        "gold_coordinates": sum(len(row["expected_articles"]) for row in cases),
        "golden_path": str(GOLDEN.relative_to(ROOT)),
        "golden_sha256": _sha256(GOLDEN),
        "public_path": str(PUBLIC.relative_to(ROOT)),
        "public_sha256": _sha256(PUBLIC),
        "scoring_path": str(SCORING.relative_to(ROOT)),
        "scoring_sha256": _sha256(SCORING),
        "audit_path": str(AUDIT.relative_to(ROOT)),
        "audit_sha256": _sha256(AUDIT),
        "dataset_sha256": ledger.deterministic_sha256({
            "golden_sha256": _sha256(GOLDEN),
            "public_sha256": _sha256(PUBLIC),
            "scoring_sha256": _sha256(SCORING),
            "audit_sha256": _sha256(AUDIT),
        }),
        "provider_calls": 0,
    }
    return receipt


def _usage(calls: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "calls": len(calls),
        "input_tokens": sum(int((row.get("provider") or {}).get("usage", {}).get("input_tokens", 0)) for row in calls),
        "output_tokens": sum(int((row.get("provider") or {}).get("usage", {}).get("output_tokens", 0)) for row in calls),
        "provider_duration_ms": sum(int((row.get("provider") or {}).get("dur_ms", 0)) for row in calls),
        "errors": sum(bool((row.get("provider") or {}).get("error")) for row in calls),
    }


def _execute_retrieval_case(legacy: Any, index: Any, case: Mapping[str, Any], real_llm: Any) -> dict[str, Any]:
    started = time.perf_counter()
    baseline_llm = legacy.RecordingLLM(real_llm)
    baseline_trace = article_reachability.ArticleReachabilityTrace(index, case["case_id"], BASELINE_ARM)
    base_started = time.perf_counter()
    base_sections, base_meta = legalclosure_runtime.retrieve(
        index, case["question"], llm=baseline_llm, assertion_llm=baseline_llm,
        cap=20, shortcut_enabled=False, feedback_enabled=False,
        graph_enabled=False, semantic_graph_enabled=False,
        integrated_research_enabled=False, reachability_trace=baseline_trace,
    )
    base_ms = round((time.perf_counter() - base_started) * 1000, 3)
    base_capture = legacy.baseline_stage_capture(index, case["case_id"], base_sections, base_meta)

    candidate_llm = legacy.RecordingLLM(real_llm)
    candidate_trace = article_reachability.ArticleReachabilityTrace(index, case["case_id"], CANDIDATE_ARM)
    candidate_started = time.perf_counter()
    cand_sections, cand_meta, shared = legacy.call_candidate_retrieve(
        legalclosure_runtime.retrieve, index, case["question"], llm=candidate_llm,
        reachability_trace=candidate_trace,
        baseline_result=(deepcopy(list(base_sections)), deepcopy(dict(base_meta))),
    )
    candidate_ms = round((time.perf_counter() - candidate_started) * 1000, 3)
    if len(cand_sections) > 32:
        raise BoundaryError(f"candidate evidence cap exceeded: {len(cand_sections)}")
    cand_capture = legacy.candidate_stage_capture(cand_meta, case["case_id"])
    candidate_metrics = legacy.integrated_execution_metrics(index, cand_sections, cand_meta)
    value = {
        "schema_version": "adr-0126-gold-free-product-capture-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "case_id": case["case_id"],
        "number": int(case["number"]),
        "suite": case["suite"],
        "question": case["question"],
        "material": case.get("material"),
        "model": MODEL,
        "gold_visible_to_product": False,
        "scope_name": index.scope_name,
        "scope_doc_ids": sorted(index.scope or ()),
        "arms": {
            BASELINE_ARM: {
                "sections": legacy._section_rows(base_sections),
                "meta": legacy._jsonable(base_meta),
                "stage_capture": base_capture,
                "provider_calls": deepcopy(baseline_llm.audit),
                "usage": _usage(baseline_llm.audit),
                "retrieval_wall_ms": base_ms,
            },
            CANDIDATE_ARM: {
                "sections": legacy._section_rows(cand_sections),
                "meta": legacy._jsonable(cand_meta),
                "stage_capture": cand_capture,
                "provider_calls": deepcopy(candidate_llm.audit),
                "usage": _usage(candidate_llm.audit),
                "retrieval_wall_ms": candidate_ms,
                "baseline_retrieval_shared": shared,
                "execution_metrics": candidate_metrics,
            },
        },
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "captured_at": _now(),
        "complete": True,
    }
    legacy._forbid_product_gold(value)
    value["capture_sha256"] = ledger.deterministic_sha256(value)
    return value


def _capture_path(case_id: str) -> Path:
    return CAPTURES / f"{case_id}.json"


def _seal_products(public: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for case in public["cases"]:
        path = _capture_path(case["case_id"])
        capture = _read_json(path)
        if capture.get("capture_sha256") != ledger.deterministic_sha256({k: v for k, v in capture.items() if k != "capture_sha256"}):
            raise BoundaryError(f"capture self hash mismatch: {case['case_id']}")
        rows.append({
            "case_id": case["case_id"],
            "path": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
            "capture_sha256": capture["capture_sha256"],
        })
    seal = {
        "schema_version": "adr-0126-product-seal-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "public_fixture_sha256": _sha256(PUBLIC),
        "gold_opened": False,
        "case_receipts": rows,
        "sealed_at": _now(),
    }
    seal["seal_sha256"] = ledger.deterministic_sha256(seal)
    _write_json(SEAL, seal)
    return seal


def _verify_product_seal(public: Mapping[str, Any]) -> None:
    if not SEAL.is_file():
        raise BoundaryError("gold cannot open before product seal")
    seal = _read_json(SEAL)
    if seal.get("public_fixture_sha256") != _sha256(PUBLIC):
        raise BoundaryError("sealed public fixture hash mismatch")
    receipts = {str(row["case_id"]): row for row in seal.get("case_receipts", [])}
    if set(receipts) != {str(row["case_id"]) for row in public["cases"]}:
        raise BoundaryError("product seal case set mismatch")
    for case in public["cases"]:
        case_id = str(case["case_id"])
        path = _capture_path(case_id)
        capture = _read_json(path)
        receipt = receipts[case_id]
        if receipt.get("sha256") != _sha256(path):
            raise BoundaryError(f"sealed capture file hash mismatch: {case_id}")
        if capture.get("capture_sha256") != receipt.get("capture_sha256"):
            raise BoundaryError(f"sealed capture self hash mismatch: {case_id}")


def _present(capture: Mapping[str, Any]) -> set[tuple[str, int]]:
    return {(str(row["doc_id"]), int(row["node"])) for row in capture["stages"][-1]["after"]}


def _write_question_markdown(case: Mapping[str, Any], score: Mapping[str, Any], product: Mapping[str, Any], grades: Mapping[str, Any]) -> Path:
    number = int(case["number"])
    path = ADR / "실험" / f"질문-{number:03d}-{case['case_id']}.md"
    lines = [
        f"# 질문 {number:03d} — {case['case_id']}", "",
        "## 1. 실행 메타", "",
        f"- ADR / experiment / run: `{ADR_ID}` / `{EXPERIMENT_ID}` / `{RUN_ID}`",
        f"- 제품·중간 모델: `{MODEL}`", "- product capture 상태: `sealed exact`",
        "- gold visible to product: `false`",
        f"- product capture: `{_capture_path(case['case_id']).relative_to(ROOT)}`", "",
        "## 2. 사용자 질문 원문", "", str(case["question"]), "",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "",
        "제품 두 arm의 전체 capture와 provider raw receipt를 봉인한 뒤 이 절을 열었다.", "", "```json",
        json.dumps(score["expected_articles"], ensure_ascii=False, indent=2), "```", "",
        "## 4. 제품 입력을 구성한 원값", "", "```json",
        json.dumps({"scope": "내규", "material": case.get("material"), "question": case["question"]}, ensure_ascii=False, indent=2),
        "```", "", "### 회수·탈락 단계 원장 — run·arm별", "",
        f"- 전수 stage ledger: `{LEDGER.relative_to(ROOT)}`",
        "- 두 arm의 exact coordinate snapshot은 product capture의 `stage_capture`에 보존했다.", "",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문", "",
        "이 probe는 최종 답변을 생성하지 않고 조문 회수만 측정하므로 answer 호출은 없다.", "",
    ]
    for arm in ARMS:
        payload = product["arms"][arm]
        lines.extend([
            f"### `{arm}` 최종 제시 조문", "", "```json",
            json.dumps(payload["sections"], ensure_ascii=False, indent=2), "```", "",
        ])
    lines.extend(["## 6. 중간 LLM 호출 — router/compiler/verifier/repair", ""])
    for arm in ARMS:
        lines.extend([
            f"### `{arm}` exact provider 입출력", "", "```json",
            json.dumps(product["arms"][arm]["provider_calls"], ensure_ascii=False, indent=2), "```", "",
        ])
    lines.extend([
        "## 7. 채점 호출과 반복 판정", "",
        "의미 judge 호출 없이 봉인 후 canonical article-root 좌표 포함 여부를 1회 결정론 채점했다.", "",
    ])
    for arm in ARMS:
        lines.extend([
            f"### `{arm}` 좌표 채점", "", "```json",
            json.dumps(grades[arm], ensure_ascii=False, indent=2), "```", "",
        ])
    paired = "both_pass" if all(grades[arm]["all_gold_hit"] for arm in ARMS) else "not_both_pass"
    lines.extend([
        "## 8. 사례 최종 판정", "",
        f"- paired outcome: `{paired}`",
        f"- baseline: `{grades[BASELINE_ARM]['gold_hits']}/{grades[BASELINE_ARM]['gold_total']}`",
        f"- candidate: `{grades[CANDIDATE_ARM]['gold_hits']}/{grades[CANDIDATE_ARM]['gold_total']}`", "",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _grade_and_finalize(public: Mapping[str, Any]) -> dict[str, Any]:
    _verify_product_seal(public)
    scoring = _read_json(SCORING)
    score_by_id = {row["case_id"]: row for row in scoring["cases"]}
    prohibited = {str(row["doc_id"]) for row in scoring["forbidden_final_documents"]}
    graded_ledgers = []
    case_rows = []
    question_files = []
    for case in public["cases"]:
        product = _read_json(_capture_path(case["case_id"]))
        score = score_by_id[case["case_id"]]
        gold = [(str(row["doc_id"]), int(row["node"])) for row in score["expected_articles"]]
        grades = {}
        presents = {}
        for arm in ARMS:
            capture = product["arms"][arm]["stage_capture"]
            graded = ledger.grade_capture(capture, gold)
            graded_ledgers.append(graded)
            presents[arm] = _present(capture)
            grades[arm] = {
                "gold_total": len(gold),
                "gold_hits": len(presents[arm] & set(gold)),
                "all_gold_hit": set(gold).issubset(presents[arm]),
                "missing": [
                    {"doc_id": doc_id, "node": node}
                    for doc_id, node in sorted(set(gold) - presents[arm])
                ],
                "prohibited_final": [
                    {"doc_id": doc_id, "node": node}
                    for doc_id, node in sorted(presents[arm]) if doc_id in prohibited
                ],
                "final_presented": len(presents[arm]),
            }
        baseline_hit = set(gold) & presents[BASELINE_ARM]
        candidate_hit = set(gold) & presents[CANDIDATE_ARM]
        case_rows.append({
            "case_id": case["case_id"],
            "number": case["number"],
            "gold_total": len(gold),
            "arms": grades,
            "candidate_only_gold": len(candidate_hit - baseline_hit),
            "baseline_only_gold": len(baseline_hit - candidate_hit),
            "paired": (
                "candidate_only" if grades[CANDIDATE_ARM]["all_gold_hit"] and not grades[BASELINE_ARM]["all_gold_hit"]
                else "baseline_only" if grades[BASELINE_ARM]["all_gold_hit"] and not grades[CANDIDATE_ARM]["all_gold_hit"]
                else "both_pass" if grades[BASELINE_ARM]["all_gold_hit"] else "both_fail"
            ),
        })
        question_files.append(_write_question_markdown(case, score, product, grades))

    declared = {
        arm: [row["stage_id"] for row in _read_json(MANIFEST)["design"]["retrieval_stage_plan"]["stages_by_arm"][arm]]
        for arm in ARMS
    }
    run_ledger = ledger.build_run_artifact(RUN_ID, graded_ledgers, declared)
    experiment_ledger = ledger.build_experiment_artifact(ADR_ID, EXPERIMENT_ID, [run_ledger])
    _write_json(LEDGER, experiment_ledger)

    by_arm = {}
    for arm in ARMS:
        captures = [_read_json(_capture_path(case_id))["arms"][arm] for case_id in EXPECTED_CASE_IDS]
        hits = sum(row["arms"][arm]["gold_hits"] for row in case_rows)
        total = sum(row["gold_total"] for row in case_rows)
        presented = [row["arms"][arm]["final_presented"] for row in case_rows]
        latencies = [float(row["retrieval_wall_ms"]) for row in captures]
        usages = [row["usage"] for row in captures]
        prohibited_count = sum(len(row["arms"][arm]["prohibited_final"]) for row in case_rows)
        by_arm[arm] = {
            "gold_hits": hits,
            "gold_total": total,
            "golden_recall": round(hits / total, 6),
            "all_gold_cases": sum(row["arms"][arm]["all_gold_hit"] for row in case_rows),
            "presented_total": sum(presented),
            "presented_mean": round(statistics.mean(presented), 6),
            "presented_p50": statistics.median(presented),
            "presented_p95": _percentile(presented, 0.95),
            "retrieval_p50_ms": _percentile(latencies, 0.5),
            "retrieval_p95_ms": _percentile(latencies, 0.95),
            "prohibited_final_count": prohibited_count,
            "usage": {
                key: sum(int(row.get(key) or 0) for row in usages)
                for key in ("calls", "input_tokens", "output_tokens", "provider_duration_ms", "errors")
            },
        }
    baseline_captures = [
        _read_json(_capture_path(case_id))["arms"][BASELINE_ARM]
        for case_id in EXPECTED_CASE_IDS
    ]
    candidate_captures = [
        _read_json(_capture_path(case_id))["arms"][CANDIDATE_ARM]
        for case_id in EXPECTED_CASE_IDS
    ]
    inclusive_latencies = [
        float(baseline["retrieval_wall_ms"]) + float(candidate["retrieval_wall_ms"])
        for baseline, candidate in zip(baseline_captures, candidate_captures, strict=True)
    ]
    inclusive_usage = {
        key: by_arm[BASELINE_ARM]["usage"][key] + by_arm[CANDIDATE_ARM]["usage"][key]
        for key in ("calls", "input_tokens", "output_tokens", "provider_duration_ms", "errors")
    }
    by_arm[CANDIDATE_ARM]["shared_floor_accounting"] = {
        "baseline_floor_shared": True,
        "reported_arm_latency_and_usage_are_incremental": True,
        "incremental_retrieval_p50_ms": by_arm[CANDIDATE_ARM]["retrieval_p50_ms"],
        "incremental_retrieval_p95_ms": by_arm[CANDIDATE_ARM]["retrieval_p95_ms"],
        "inclusive_retrieval_p50_ms": _percentile(inclusive_latencies, 0.5),
        "inclusive_retrieval_p95_ms": _percentile(inclusive_latencies, 0.95),
        "inclusive_usage": inclusive_usage,
    }
    baseline_recall = by_arm[BASELINE_ARM]["golden_recall"]
    success = (
        by_arm[CANDIDATE_ARM]["golden_recall"] >= baseline_recall
        and by_arm[CANDIDATE_ARM]["all_gold_cases"] >= by_arm[BASELINE_ARM]["all_gold_cases"]
        and sum(row["baseline_only_gold"] for row in case_rows) == 0
        and (sum(row["candidate_only_gold"] for row in case_rows) >= 2 or baseline_recall >= 0.95)
        and by_arm[CANDIDATE_ARM]["prohibited_final_count"] == 0
        and by_arm[CANDIDATE_ARM]["presented_p95"] <= 32
        and by_arm[CANDIDATE_ARM]["retrieval_p95_ms"] <= 180000
        and by_arm[CANDIDATE_ARM]["usage"]["errors"] == 0
    )
    run = {
        "schema_version": "adr-0126-internal-retrieval-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "gold_opened_after_product_seal": True,
        "product_seal_path": str(SEAL.relative_to(ROOT)),
        "product_seal_sha256": _sha256(SEAL),
        "public_fixture_sha256": _sha256(PUBLIC),
        "scoring_fixture_sha256": _sha256(SCORING),
        "data_audit_sha256": _sha256(AUDIT),
        "ledger_path": str(LEDGER.relative_to(ROOT)),
        "ledger_sha256": _sha256(LEDGER),
        "by_arm": by_arm,
        "paired": {
            "candidate_only_cases": sum(row["paired"] == "candidate_only" for row in case_rows),
            "baseline_only_cases": sum(row["paired"] == "baseline_only" for row in case_rows),
            "both_pass_cases": sum(row["paired"] == "both_pass" for row in case_rows),
            "both_fail_cases": sum(row["paired"] == "both_fail" for row in case_rows),
            "candidate_only_gold": sum(row["candidate_only_gold"] for row in case_rows),
            "baseline_only_gold": sum(row["baseline_only_gold"] for row in case_rows),
        },
        "cases": case_rows,
        "success_criteria_passed": success,
        "status": "complete",
        "completed_at": _now(),
        "question_files": [str(path.relative_to(ROOT)) for path in question_files],
    }
    run["run_sha256"] = ledger.deterministic_sha256(run)
    _write_json(RUN, run)
    return run


def run_probe(*, resume: bool = False) -> dict[str, Any]:
    manifest = _read_json(MANIFEST)
    if manifest["design"].get("criteria_frozen_before_run") is not True:
        raise BoundaryError("manifest criteria must be frozen before provider calls")
    prepared = prepare_fixtures()
    if manifest["dataset"].get("sha256") != prepared["dataset_sha256"]:
        raise BoundaryError("manifest dataset hash differs from frozen fixtures")
    public = _read_json(PUBLIC)
    if any("expected_articles" in row for row in public["cases"]):
        raise BoundaryError("gold leaked into public fixture")
    index, scope_info = scopes_mod.apply(index_mod.current(), scope="내규")
    if set(scope_info["doc_ids"]) != set(CURRENT_INTERNAL_DOC_IDS):
        raise BoundaryError("internal scope differs from frozen current documents")
    legacy = _legacy_runner()
    contract = legacy.runtime_adapter_contract(legalclosure_runtime.retrieve)
    if not contract["ready"]:
        raise BoundaryError(f"ADR-0114 runtime contract is not ready: {contract}")
    real_llm = legacy._make_llm()
    CAPTURES.mkdir(parents=True, exist_ok=True)
    for position, case in enumerate(public["cases"], 1):
        path = _capture_path(case["case_id"])
        if resume and path.is_file():
            print(f"[resume {position}/12] {case['case_id']}", flush=True)
            continue
        if path.exists():
            raise BoundaryError(f"existing capture requires --resume: {path}")
        capture = _execute_retrieval_case(legacy, index, case, real_llm)
        _write_json(path, capture)
        print(f"[product {position}/12] {case['case_id']}", flush=True)
    _seal_products(public)
    return _grade_and_finalize(public)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--prepare-fixtures", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--regrade-sealed", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1,), default=1)
    args = parser.parse_args(argv)
    selected = sum((args.audit_only, args.prepare_fixtures, args.run, args.regrade_sealed))
    if selected != 1:
        parser.error("choose exactly one of --audit-only, --prepare-fixtures, --run, --regrade-sealed")
    if args.audit_only:
        result = audit_internal_data()
    elif args.prepare_fixtures:
        result = prepare_fixtures()
    elif args.regrade_sealed:
        result = _grade_and_finalize(_read_json(PUBLIC))
    else:
        result = run_probe(resume=args.resume)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
