#!/usr/bin/env python3
"""현재 설정에서 정확히 한 스위치만 바꾼 RAG ablation 실행판을 만든다.

    .venv/bin/python scripts/rag_ablation_plan.py --output-dir var/eval/ablation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from lawrag.core.rag import evaluation

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output-dir", type=Path,
                    help="baseline.engine.json과 후보별 engine JSON을 저장")
    ap.add_argument("--only", action="append", default=[],
                    help="ablation key만 선택(여러 번 지정)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    baseline = evaluation.engine_snapshot()
    base_values = {row["key"]: bool(row["on"]) for row in baseline["values"]}
    wanted = set(args.only)
    specs = [spec for spec in evaluation.ABLATIONS if not wanted or spec.key in wanted]
    unknown = wanted - {spec.key for spec in evaluation.ABLATIONS}
    if unknown:
        print(f"모르는 ablation: {sorted(unknown)}", file=sys.stderr)
        return 2
    matrix = {"baseline": baseline, "experiments": []}
    for spec in specs:
        before = base_values.get(spec.switch)
        candidate = dict(base_values)
        candidate[spec.switch] = spec.candidate_on
        matrix["experiments"].append({
            "key": spec.key, "purpose": spec.purpose, "switch": spec.switch,
            "before": before, "after": spec.candidate_on,
            "valid_one_variable": before != spec.candidate_on,
            "switches": candidate,
        })
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "baseline.engine.json").write_text(
            json.dumps({"switches": base_values}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        for row in matrix["experiments"]:
            (args.output_dir / f"{row['key']}.engine.json").write_text(
                json.dumps({"switches": row["switches"]}, ensure_ascii=False,
                           indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(matrix, ensure_ascii=False, indent=2))
    else:
        print(f"기준 {baseline['fingerprint']} · ablation {len(matrix['experiments'])}개")
        for row in matrix["experiments"]:
            mark = "○" if row["valid_one_variable"] else "-"
            print(f"  {mark} {row['key']}: {row['switch']}"
                  f" {row['before']} → {row['after']} · {row['purpose']}")
        if args.output_dir:
            print(f"실행판 저장: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

