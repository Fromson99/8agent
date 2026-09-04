#!/usr/bin/env python3
"""ADR-0038의 paired 불일치 답변만 Haiku 2표 추가해 3표 다수결한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402
from scripts.rag_definition_context_answer_ab import (  # noqa: E402
    HAIKU, JUDGE_SCHEMA, JUDGE_SYSTEM,
)
from scripts.rag_legal_issue_e2e_eval import _usage  # noqa: E402


def _majority(votes: list[dict], name: str) -> bool:
    return sum(bool(vote[name]["correct"]) for vote in votes) >= 2


def _prompt(row: dict, swapped: bool) -> tuple[dict, str]:
    baseline = row["baseline"]["answer"]
    candidate = row["candidate"]["answer"]
    if swapped:
        mapping = {"baseline": "B", "candidate": "A"}
        a, b = candidate, baseline
    else:
        mapping = {"baseline": "A", "candidate": "B"}
        a, b = baseline, candidate
    user = (f"[기준답변]\n{row['reference_answer']}\n\n"
            f"[답변 A]\n{a}\n\n[답변 B]\n{b}")
    return mapping, user


def _summary(rows):
    baseline = sum(row["majority"]["baseline"] for row in rows)
    candidate = sum(row["majority"]["candidate"] for row in rows)
    return {
        "cases": len(rows), "baseline_correct": baseline,
        "candidate_correct": candidate, "delta": candidate - baseline,
        "paired": {
            "both_correct": sum(row["majority"]["baseline"]
                                and row["majority"]["candidate"] for row in rows),
            "baseline_only": sum(row["majority"]["baseline"]
                                 and not row["majority"]["candidate"] for row in rows),
            "candidate_only": sum(not row["majority"]["baseline"]
                                  and row["majority"]["candidate"] for row in rows),
            "both_incorrect": sum(not row["majority"]["baseline"]
                                  and not row["majority"]["candidate"] for row in rows),
        },
        "added_judge_usage": {key: sum(row["added_usage"][key] for row in rows)
                              for key in ("calls", "input_tokens", "output_tokens",
                                          "duration_ms", "errors")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "var/eval/e2e/ADR-0038/definition_context_answer_ab_51.json")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "var/eval/e2e/ADR-0038/definition_context_answer_ab_disputed19_regrade3.json")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--manifest-existing", action="store_true",
                        help="이미 저장된 --out을 LLM 재호출 없이 manifest에 등록")
    args = parser.parse_args()
    if args.manifest_existing:
        result = json.loads(args.out.read_text("utf-8"))
        digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
        artifact_dir = ROOT / "docs/adr/ADR-0038-definition-context-wiki-hygiene/artifacts"
        manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
        key = ("definition_only_regrade3" if "definition_only" in args.out.name
               else "answer_ab_regrade3")
        manifest[key] = {
            "raw_result": str(args.out.resolve().relative_to(ROOT)),
            "sha256": digest, "bytes": args.out.stat().st_size,
            "summary": result["summary"],
        }
        (artifact_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 0
    source = json.loads(args.input.read_text("utf-8"))
    disputed = [row for row in source["rows"]
                if row["judge"]["baseline"]["correct"]
                != row["judge"]["candidate"]["correct"]]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU:
        raise SystemExit("Haiku model contract failed")
    local = threading.local()

    def evaluate(row):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        votes = [{
            "baseline": row["judge"]["baseline"],
            "candidate": row["judge"]["candidate"],
            "source": "original",
        }]
        log0 = len(llm.log)
        # 한 번은 기존 배치의 반대, 한 번은 기존 parity 배치를 재사용한다.
        original_swapped = row["judge_order"]["candidate"] == "A"
        for repeat, swapped in enumerate((not original_swapped, original_swapped), 2):
            mapping, user = _prompt(row, swapped)
            judged = llm.structured(
                f"eval.adr0038.paired.regrade{repeat}", JUDGE_SYSTEM, user,
                JUDGE_SCHEMA, max_tokens=1400, effort="medium", model=HAIKU)
            if judged is None:
                raise RuntimeError(f"judge repeat {repeat} failed")
            votes.append({
                name: {"correct": bool(judged[label]["correct"]),
                       "reason": str(judged[label]["reason"])[:800]}
                for name, label in mapping.items()
            } | {"source": f"repeat{repeat}", "swapped": swapped})
        return {
            "case_no": row["case_no"], "votes": votes,
            "majority": {name: _majority(votes, name)
                         for name in ("baseline", "candidate")},
            "added_usage": _usage(list(llm.log)[log0:]),
            "definition_entries": row["candidate"].get("definition_entries",
                                                        len(row.get("definition_appendix") or [])),
            "wiki": row["candidate"].get("wiki", []),
        }

    rows, order = [], {row["case_no"]: i for i, row in enumerate(disputed)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): row["case_no"] for row in disputed}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_no = futures[future]
            row = future.result()
            rows.append(row)
            rows.sort(key=lambda item: order[item["case_no"]])
            print(f"[{position:02d}/{len(disputed)}] {case_no} "
                  f"B={'○' if row['majority']['baseline'] else '✗'} "
                  f"C={'○' if row['majority']['candidate'] else '✗'}", flush=True)
    result = {
        "experiment": "ADR-0038-definition-context-answer-disputed-regrade3",
        "model": HAIKU, "source": str(args.input),
        "summary": _summary(rows), "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    artifact_dir = ROOT / "docs/adr/ADR-0038-definition-context-wiki-hygiene/artifacts"
    manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
    key = ("definition_only_regrade3" if "definition_only" in args.out.name
           else "answer_ab_regrade3")
    manifest[key] = {
        "raw_result": str(args.out.resolve().relative_to(ROOT)), "sha256": digest,
        "bytes": args.out.stat().st_size, "summary": result["summary"],
    }
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
