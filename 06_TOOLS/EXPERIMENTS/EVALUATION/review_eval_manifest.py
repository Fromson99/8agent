#!/usr/bin/env python3
"""기존 법률검토 골든 실행을 공통 RAG 평가 manifest로 변환한다.

    .venv/bin/python scripts/review_eval_manifest.py \
      data/review/golden_mix2080_v3.json var/eval/review-v3.json --label v3
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
DEFAULT_LABELS = ROOT / "01_DATA" / "review" / "golden_labels.json"


def main() -> int:
    from lawrag.core.rag import evaluation

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path, help="review_golden.py가 만든 rows JSON")
    ap.add_argument("output", type=Path, help="공통 평가 manifest JSON")
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    ap.add_argument("--suite", type=Path,
                    help="raw에 내장된 suite 대신 사용할 동결 suite JSON")
    ap.add_argument("--flow", choices=("ask", "legal_review"),
                    help="같은 사건판을 통과한 실제 제품 흐름")
    ap.add_argument("--label", default="")
    ap.add_argument("--trial", type=int, default=1)
    args = ap.parse_args()
    blob = json.loads(args.input.read_text(encoding="utf-8"))
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    source_suite = (json.loads(args.suite.read_text(encoding="utf-8"))
                    if args.suite else blob.get("suite"))
    source_flow = str(args.flow or blob.get("flow")
                      or ("ask" if (source_suite or {}).get("cases")
                          else "legal_review"))
    manifest = evaluation.build_review_manifest(
        source_path=args.input, source_rows=blob.get("rows") or [], labels=labels,
        run_label=args.label or args.input.stem, trial=args.trial,
        source_flow=source_flow,
        source_suite=source_suite,
        source_controls=blob.get("controls"), source_engine=blob.get("engine"),
        source_variant=blob.get("variant"))
    evaluation.write_manifest(args.output, manifest)
    metrics = manifest["summary"]["metrics"]
    direction = (f"방향 {metrics['direction_accuracy']:.1%}"
                 if not metrics.get("semantic_cases") else "방향 n/a(명제 채점)")
    combined = (f"명제+근거 {metrics['semantic_basis_rate']:.1%}"
                if metrics.get("semantic_cases")
                else f"방향+근거 {metrics['direction_basis_rate']:.1%}")
    channel = (f"채널 {metrics['required_channel_coverage']:.1%}"
               if manifest["suite"].get("required_channels") else "채널 n/a")
    print(f"검토 manifest {args.output} · {metrics['cases']}건"
          f" · {direction}"
          f" · 조문 {metrics['article_recall']:.1%}"
          f" · 근거 {metrics['basis_recall']:.1%}"
          f" · {combined}"
          + (f" · 명제 {metrics['semantic_accuracy']:.1%}"
             if metrics.get("semantic_cases") else "")
          + f" · {channel}"
          + f" · 단계 {metrics['required_stage_coverage']:.1%}"
          f" · controls={manifest['controls']['fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
