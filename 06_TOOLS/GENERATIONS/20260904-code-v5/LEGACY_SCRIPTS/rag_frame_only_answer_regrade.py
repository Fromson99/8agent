#!/usr/bin/env python3
"""ADR-0040의 paired 불일치 사례만 Haiku 2표를 추가해 3표 다수결한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import threading


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import review_golden as review  # noqa: E402
from scripts.rag_definition_context_answer_ab import (  # noqa: E402
    HAIKU, JUDGE_SCHEMA, JUDGE_SYSTEM,
)
from scripts.rag_legal_issue_e2e_eval import _usage  # noqa: E402


def _prompt(row: dict, swapped: bool) -> tuple[dict, str]:
    if swapped:
        mapping = {"original": "B", "frame_only": "A"}
        a, b = row["frame_only"]["answer"], row["original"]["answer"]
    else:
        mapping = {"original": "A", "frame_only": "B"}
        a, b = row["original"]["answer"], row["frame_only"]["answer"]
    user = (f"[기준답변]\n{row['reference_answer']}\n\n"
            f"[답변 A]\n{a}\n\n[답변 B]\n{b}")
    return mapping, user


def _majority(votes: list[dict], name: str) -> bool:
    return sum(bool(vote[name]["correct"]) for vote in votes) >= 2


def _summary(source_rows: list[dict], regraded: list[dict]) -> dict:
    by_case = {row["case_no"]: row for row in regraded}
    final = []
    for row in source_rows:
        if row["case_no"] in by_case:
            marks = by_case[row["case_no"]]["majority"]
        else:
            marks = {name: bool(row["judge"][name]["correct"])
                     for name in ("original", "frame_only")}
        final.append(marks)
    original = sum(row["original"] for row in final)
    frame_only = sum(row["frame_only"] for row in final)
    return {
        "cases": len(final), "regraded_disputed_cases": len(regraded),
        "original_correct": original,
        "original_accuracy": round(original / len(final), 4) if final else 0,
        "frame_only_correct": frame_only,
        "frame_only_accuracy": round(frame_only / len(final), 4) if final else 0,
        "delta": frame_only - original,
        "paired": {
            "both_correct": sum(x["original"] and x["frame_only"] for x in final),
            "original_only": sum(x["original"] and not x["frame_only"] for x in final),
            "frame_only_only": sum(not x["original"] and x["frame_only"] for x in final),
            "both_incorrect": sum(not x["original"] and not x["frame_only"] for x in final),
        },
        "added_judge_usage": {key: sum(row["added_usage"][key] for row in regraded)
                              for key in ("calls", "input_tokens", "output_tokens",
                                          "duration_ms", "errors")},
    }


def _append_case_markdown(rows: list[dict]) -> None:
    case_dir = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0040-frame-only-legal-answer-ab/cases"
    existing = {path.name.split("-", 1)[1][:-3]: path
                for path in case_dir.glob("[0-9][0-9][0-9]-cm-*.md")}
    for row in rows:
        path = existing.get(row["case_no"])
        if path is None:
            continue
        parts = ["\n## Haiku judge 3표 다수결\n"]
        for vote in row["votes"]:
            parts.append(
                f"\n### {vote['source']}\n\n"
                f"- A/B mapping: `{json.dumps(vote['mapping'], ensure_ascii=False)}`\n"
                f"- 판정: original=`{vote['original']['correct']}`, "
                f"frame_only=`{vote['frame_only']['correct']}`\n"
            )
            if vote.get("system_prompt"):
                parts.append(f"\n#### system\n\n```text\n{vote['system_prompt']}\n```\n")
            if vote.get("user_prompt"):
                parts.append(f"\n#### user\n\n```text\n{vote['user_prompt']}\n```\n")
            if vote.get("raw") is not None:
                parts.append(
                    f"\n#### 구조화 출력\n\n```json\n"
                    f"{json.dumps(vote['raw'], ensure_ascii=False, indent=2)}\n```\n")
        parts.append(
            f"\n### 다수결\n\n"
            f"- original: **{row['majority']['original']}**\n"
            f"- frame_only: **{row['majority']['frame_only']}**\n"
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write("".join(parts))


def _refresh_case_manifest() -> dict:
    case_dir = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0040-frame-only-legal-answer-ab/cases"
    files = []
    for path in sorted(case_dir.glob("[0-9][0-9][0-9]-cm-*.md")):
        files.append({
            "case_no": path.stem.split("-", 1)[1],
            "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    readme = case_dir / "README.md"
    manifest = {
        "files": files,
        "readme_sha256": hashlib.sha256(readme.read_bytes()).hexdigest(),
    }
    target = case_dir / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"directory": str(case_dir.relative_to(ROOT)), "files": len(files),
            "manifest": str(target.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0040/frame_only_answer_ab_51.json")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0040/frame_only_answer_ab_disputed35_regrade3.json")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--refresh-case-manifest-only", action="store_true")
    args = parser.parse_args()

    if args.refresh_case_manifest_only:
        print(json.dumps(_refresh_case_manifest(), ensure_ascii=False, indent=1))
        return 0

    source = json.loads(args.input.read_text("utf-8"))
    source_rows = [row for row in source["rows"] if not row.get("error")]
    disputed = [row for row in source_rows
                if row["judge"]["original"]["correct"]
                != row["judge"]["frame_only"]["correct"]]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU:
        raise SystemExit("Haiku model contract failed")
    local = threading.local()

    def evaluate(row):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm is None or local.llm.model != HAIKU:
                raise RuntimeError("worker model is not Haiku")
        llm = local.llm
        first_mapping = row["judge_order"]
        votes = [{
            "source": "original", "mapping": first_mapping,
            "original": row["judge"]["original"],
            "frame_only": row["judge"]["frame_only"],
            "system_prompt": row["judge_system_prompt"],
            "user_prompt": row["judge_user_prompt"], "raw": row["judge_raw"],
        }]
        log0 = len(llm.log)
        original_swapped = first_mapping["frame_only"] == "A"
        for repeat, swapped in enumerate((not original_swapped, original_swapped), 2):
            mapping, user = _prompt(row, swapped)
            judged = llm.structured(
                f"eval.adr0040.paired.regrade{repeat}", JUDGE_SYSTEM, user,
                JUDGE_SCHEMA, max_tokens=1400, effort="medium", model=HAIKU)
            if judged is None:
                raise RuntimeError(f"judge repeat {repeat} failed")
            vote = {
                "source": f"repeat{repeat}", "mapping": mapping,
                "system_prompt": JUDGE_SYSTEM, "user_prompt": user, "raw": judged,
            }
            for name, label in mapping.items():
                vote[name] = {"correct": bool(judged[label]["correct"]),
                              "reason": str(judged[label]["reason"])[:800]}
            votes.append(vote)
        return {
            "case_no": row["case_no"], "votes": votes,
            "majority": {name: _majority(votes, name)
                         for name in ("original", "frame_only")},
            "added_usage": _usage(list(llm.log)[log0:]),
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
                  f"O={'○' if row['majority']['original'] else '✗'} "
                  f"F={'○' if row['majority']['frame_only'] else '✗'}", flush=True)
    result = {
        "experiment": "ADR-0040-frame-only-disputed-regrade3",
        "model": HAIKU, "source": str(args.input.relative_to(ROOT)),
        "summary": _summary(source_rows, rows), "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _append_case_markdown(rows)
    result["case_markdown"] = _refresh_case_manifest()
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
