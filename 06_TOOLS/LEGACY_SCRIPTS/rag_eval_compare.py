#!/usr/bin/env python3
"""두 RAG 평가 manifest를 안전·회수·비용 축으로 비교한다.

    .venv/bin/python scripts/rag_eval_compare.py baseline.json candidate.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))


def main() -> int:
    from lawrag.core.rag import evaluation

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("baseline", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--quality-tolerance", type=float, default=0.0,
                    help="확률적 품질 지표에 허용할 절대 하락폭")
    ap.add_argument("--json", action="store_true", help="기계 판독 JSON 출력")
    ap.add_argument("--out", type=Path, help="비교 판정 JSON 저장")
    ap.add_argument("--one-variable", action="store_true",
                    help="성능 손잡이/스위치 차이가 정확히 하나인지 강제")
    args = ap.parse_args()
    base = evaluation.load_manifest(args.baseline)
    candidate = evaluation.load_manifest(args.candidate)
    if base.get("kind") == "rag_search_benchmark" and \
            candidate.get("kind") == "rag_search_benchmark":
        report = evaluation.compare_search_benchmarks(
            base, candidate, require_one_change=args.one_variable)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"판정: {report['verdict']} · 같은 시험판={report['compatible']}")
            for row in report["configuration_diff"]:
                print(f"  Δ {row['kind']} {row['key']}: "
                      f"{row['before']} → {row['after']}")
            for key, delta in report["deltas"].items():
                print(f"  {key:<40} {delta:+.6f}")
            print(f"  좌표집합 변경 {report['changed_cases']}건 · "
                  f"품질 회귀 {len(report['quality_regression_cases'])}건")
            print("  가이드 " + json.dumps(report["guide"], ensure_ascii=False))
            for row in report["warnings"]:
                print(f"  ! {row['measure']}: {row['before']:.3f} → "
                      f"{row['after']:.3f} ({row['ratio']:+.0%})")
        return 1 if report["verdict"] in ("invalid", "regressed") else 0
    report = evaluation.compare_manifests(
        base, candidate, quality_tolerance=args.quality_tolerance,
        require_one_change=args.one_variable)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"판정: {report['verdict']} · 같은 시험판={report['compatible']}")
        print(f"성능 손잡이: {report['base']['controls']}"
              f" → {report['candidate']['controls']}")
        print(f"설정 차이 {len(report['configuration_diff'])}개")
        for row in report["configuration_diff"]:
            print(f"  Δ {row['kind']} {row['key']}:"
                  f" {row['before']} → {row['after']}")
        for key in ("positive_recall", "negative_block_rate", "source_accuracy",
                    "contamination_rate", "input_tokens_per_case",
                    "calls_per_case", "duration_ms_p95"):
            print(f"  {key:<26} {report['deltas'][key]:+.6f}")
        for row in report["regressions"]:
            print(f"  ✗ {row['label']}: {row['before']:.6f}"
                  f" → {row['after']:.6f} ({row['delta']:+.6f})")
        for row in report["warnings"]:
            print(f"  ! {row['label']}: {row['before']:.3f}"
                  f" → {row['after']:.3f} ({row['ratio']:+.0%})")
        if report["incompatible"]:
            print("  비교 불가: " + ", ".join(report["incompatible"]))
    return 1 if report["verdict"] in ("invalid", "regressed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
