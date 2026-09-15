#!/usr/bin/env python3
"""ADR-0041 ABC 판정 불일치 사례를 Haiku 3표 다수결한다."""

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
from scripts.rag_definition_context_answer_ab import HAIKU  # noqa: E402
from scripts.rag_inline_definition_card_answer_abc import (  # noqa: E402
    ADR_DIR, JUDGE_SCHEMA, JUDGE_SYSTEM, VARIANTS,
)
from scripts.rag_legal_issue_e2e_eval import _usage  # noqa: E402


def _judge_prompt(row: dict, order: tuple[str, ...]) -> tuple[dict, str]:
    mapping = {name: chr(65 + pos) for pos, name in enumerate(order)}
    user = f"[기준답변]\n{row['reference_answer']}"
    for name in order:
        user += f"\n\n[답변 {mapping[name]}]\n{row[name]['answer']}"
    return mapping, user


def _majority(votes: list[dict], name: str) -> bool:
    return sum(bool(vote[name]["correct"]) for vote in votes) >= 2


def _summary(source_rows: list[dict], regraded: list[dict]) -> dict:
    by_case = {row["case_no"]: row for row in regraded}
    final = []
    for row in source_rows:
        marks = (by_case[row["case_no"]]["majority"] if row["case_no"] in by_case else
                 {name: bool(row["judge"][name]["correct"]) for name in VARIANTS})
        final.append(marks)
    return {
        "cases": len(final), "regraded_disputed_cases": len(regraded),
        "correct": {name: sum(row[name] for row in final) for name in VARIANTS},
        "accuracy": {name: round(sum(row[name] for row in final) / len(final), 4)
                     for name in VARIANTS},
        "patterns": {
            "all_correct": sum(all(row[name] for name in VARIANTS) for row in final),
            "all_incorrect": sum(not any(row[name] for name in VARIANTS) for row in final),
            "raw_only": sum(row[VARIANTS[0]] and not row[VARIANTS[1]]
                            and not row[VARIANTS[2]] for row in final),
            "inline_only": sum(not row[VARIANTS[0]] and row[VARIANTS[1]]
                               and not row[VARIANTS[2]] for row in final),
            "no_definitions_only": sum(not row[VARIANTS[0]] and not row[VARIANTS[1]]
                                       and row[VARIANTS[2]] for row in final),
        },
        "added_judge_usage": {key: sum(row["added_usage"][key] for row in regraded)
                              for key in ("calls", "input_tokens", "output_tokens",
                                          "duration_ms", "errors")},
    }


def _append_cases(rows: list[dict]) -> dict:
    case_dir = ADR_DIR / "cases-inline-abc"
    paths = {path.stem.split("-", 1)[1]: path
             for path in case_dir.glob("[0-9][0-9][0-9]-cm-*.md")}
    for row in rows:
        path = paths[row["case_no"]]
        marker = "\n## Haiku ABC judge 3표 다수결\n"
        base = path.read_text("utf-8").split(marker, 1)[0]
        parts = ["\n## Haiku ABC judge 3표 다수결\n"]
        for vote in row["votes"]:
            parts.extend([
                f"\n### {vote['source']}\n",
                f"- mapping: `{json.dumps(vote['mapping'], ensure_ascii=False)}`\n",
                "#### system\n", f"```text\n{vote['system_prompt']}\n```\n",
                "#### user\n", f"```text\n{vote['user_prompt']}\n```\n",
                "#### 출력\n", "```json\n" + json.dumps(vote["raw"],
                                                       ensure_ascii=False, indent=2)
                + "\n```\n",
            ])
        parts.extend(["\n### 다수결\n", "```json\n" + json.dumps(
            row["majority"], ensure_ascii=False, indent=2) + "\n```\n"])
        path.write_text(base + "\n".join(parts), "utf-8")
    manifest = {"files": []}
    for path in sorted(case_dir.glob("[0-9][0-9][0-9]-cm-*.md")):
        manifest["files"].append({
            "case_no": path.stem.split("-", 1)[1],
            "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    target = case_dir / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"directory": str(case_dir.relative_to(ROOT)), "files": len(manifest["files"]),
            "manifest": str(target.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0041/inline_definition_card_answer_abc_51.json")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0041/inline_definition_card_answer_abc_disputed31_regrade3.json")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()

    source = json.loads(args.input.read_text("utf-8"))
    source_rows = [row for row in source["rows"] if not row.get("error")]
    disputed = [row for row in source_rows
                if len({bool(row["judge"][name]["correct"]) for name in VARIANTS}) > 1]
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
        initial_order = tuple(sorted(VARIANTS, key=lambda name: row["judge_order"][name]))
        votes = [{"source": "original", "mapping": row["judge_order"],
                  "system_prompt": row["judge_system_prompt"],
                  "user_prompt": row["judge_user_prompt"], "raw": row["judge_raw"],
                  **row["judge"]}]
        log0 = len(llm.log)
        for repeat, shift in enumerate((1, 2), 2):
            order = initial_order[shift:] + initial_order[:shift]
            mapping, user = _judge_prompt(row, order)
            judged = llm.structured(
                f"eval.adr0041.abc.regrade{repeat}", JUDGE_SYSTEM, user,
                JUDGE_SCHEMA, max_tokens=2000, effort="medium", model=HAIKU)
            if judged is None:
                raise RuntimeError(f"judge repeat {repeat} failed")
            vote = {"source": f"repeat{repeat}", "mapping": mapping,
                    "system_prompt": JUDGE_SYSTEM, "user_prompt": user, "raw": judged}
            vote.update({name: {"correct": bool(judged[mapping[name]]["correct"]),
                                "reason": str(judged[mapping[name]]["reason"])[:800]}
                         for name in VARIANTS})
            votes.append(vote)
        return {"case_no": row["case_no"], "votes": votes,
                "majority": {name: _majority(votes, name) for name in VARIANTS},
                "added_usage": _usage(list(llm.log)[log0:])}

    rows, positions = [], {row["case_no"]: i for i, row in enumerate(disputed)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): row["case_no"] for row in disputed}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_no = futures[future]
            row = future.result()
            rows.append(row)
            rows.sort(key=lambda item: positions[item["case_no"]])
            print(f"[{position:02d}/{len(disputed)}] {case_no} " + " ".join(
                f"{name[:2]}={'○' if row['majority'][name] else '✗'}" for name in VARIANTS),
                flush=True)
    result = {"experiment": "ADR-0041-inline-definition-abc-regrade3",
              "model": HAIKU, "source": str(args.input.relative_to(ROOT)),
              "summary": _summary(source_rows, rows), "rows": rows}
    result["case_markdown"] = _append_cases(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
