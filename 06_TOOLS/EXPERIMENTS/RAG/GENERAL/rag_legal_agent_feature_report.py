#!/usr/bin/env python3
"""독립 기능 실험을 LegalClosure 운영 게이트 기준으로 한 장에 합친다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--auditor", type=Path, required=True)
    parser.add_argument("--shortcut", type=Path, required=True)
    parser.add_argument("--validity", type=Path, required=True)
    parser.add_argument("--rescue", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline = _read(args.baseline)
    requirements = _read(args.requirements)
    auditor = _read(args.auditor)
    shortcut = _read(args.shortcut)
    validity = _read(args.validity)
    rescue = _read(args.rescue)

    b = baseline["summary"]
    req = requirements["summary"]
    ans = auditor["summary"]["answer"]
    cost = auditor["summary"]["cost"]["issue_frame_and_judge"]
    warm = shortcut["summary"]["warm"]
    meta = validity["corpus"]["metadata_coverage"]
    rescue_summary = rescue["summary"]
    features = [
        {
            "feature": "source_spanned_normative_requirements",
            "status": "shadow_pass",
            "evidence": {
                "coordinates": req["audited_coordinates"],
                "spans": req["spans"],
                "elapsed_seconds": req["elapsed_seconds"],
                "gold_question_coverage_proxy": req["gold_question_coverage"],
            },
            "reason": "offset과 폐쇄 cue는 재현되나 의미 정확도 표본검수 전에는 canonical 자동 발행 금지",
        },
        {
            "feature": "requirement_card_evidence_auditor",
            "status": "production_fail",
            "evidence": {
                "semantic_correct": ans["semantic_correct"],
                "cases": ans["cases"] if "cases" in ans else auditor["summary"]["cases"],
                "semantic_accuracy": ans["semantic_accuracy"],
                "product_errors": cost["errors"],
                "downstream_p50_ms": auditor["summary"]["latency"]["downstream_product_wall_ms_p50"],
            },
            "reason": "31/51과 2회 출력 절단은 기본 답변기로 승격할 수 없음",
        },
        {
            "feature": "canonical_typed_assertion_shortcut",
            "status": "production_fail",
            "evidence": {
                "baseline_gold": b["selected_hits"],
                "shortcut_gold": warm["selected_hits"],
                "shortcut_hits": warm["shortcut_hits"],
                "saved_calls": warm["saved_calls"],
                "assertion_cap_violations": warm["assertion_cap_violations"],
            },
            "reason": "ROLE:Concept만으로 route를 식별하면 68/70이 67/70으로 회귀",
        },
        {
            "feature": "temporal_authority_gate",
            "status": "shadow_only",
            "evidence": {
                "documents": validity["corpus"]["documents"],
                "enforce_coverage": meta["enforce"]["rate"],
                "series_coverage": meta["series"]["rate"],
                "version_coverage": meta["version"]["rate"],
                "dated_eval_cases": validity["suite"]["explicit_full_date_cases"],
            },
            "reason": "경고는 가능하지만 구법 원문·종료일과 시점 질문 평가셋이 부족",
        },
        {
            "feature": "conditional_dense_or_colbert_rescue",
            "status": "not_needed_for_current_errors",
            "evidence": {
                "candidate_upper_recall": rescue_summary["candidate_upper_recall"],
                "selection_miss": rescue_summary["selection_miss"],
                "retrieval_miss": rescue_summary["retrieval_miss"],
            },
            "reason": "현재 2개 오답은 후보에 이미 있으므로 선택기 문제",
        },
    ]
    result = {
        "experiment": "legal-agent-feature-integration-report-v1",
        "baseline": {
            "main": "LegalClosure",
            "cases": b["cases"],
            "gold": b["gold"],
            "selected_hits": b["selected_hits"],
            "selected_recall": b["selected_recall"],
            "case_hits": b["case_hits"],
            "unchanged_by_shadow_experiments": True,
        },
        "release_rule": {
            "retrieval_floor": "68/70",
            "assertion_cap": 8,
            "main_topology": "LegalClosure A/B/C/D preserved",
            "no_shadow_feature_auto_enabled": True,
        },
        "features": features,
        "decision": {
            "keep": ["LegalClosure main", "source-span requirement metadata in shadow"],
            "revise": ["shortcut key with scope/function/condition/authority/as_of",
                       "auditor schema and truncation handling"],
            "defer": ["historical answer automation", "Dense/ColBERT main channel"],
        },
        "sources": {key: str(getattr(args, key)) for key in
                    ("baseline", "requirements", "auditor", "shortcut", "validity", "rescue")},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps({"baseline": result["baseline"], "features": features},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
