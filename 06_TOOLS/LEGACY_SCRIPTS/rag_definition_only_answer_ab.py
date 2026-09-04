#!/usr/bin/env python3
"""ADR-0038: 정의 제거 영향 27건을 같은 현재 Wiki에서 fresh/fresh Haiku A/B한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import review_golden as review  # noqa: E402
from lawrag.core.rag import answer, legal_coordinates  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.rag_definition_context_answer_ab import (  # noqa: E402
    HAIKU, JUDGE_SCHEMA, JUDGE_SYSTEM,
)
from scripts.rag_legal_issue_e2e_eval import _percentile, _usage  # noqa: E402


def _sections(index, selected, appendix=None):
    rows = []
    for position, item in enumerate(selected, 1):
        view = index.docs[item["doc_id"]]
        rows.append(Section(
            n=position, doc_id=item["doc_id"], doc=item["doc"], node=item["node"],
            path=item["path"], page=view.by_id[item["node"]].get("page"),
            kind="법률좌표폐쇄", matched=item.get("origin") or "frozen",
            text=legal_coordinates.subtree_text(view, item["node"], cap=None)))
    for item in appendix or []:
        target = next((row for row in rows if row.doc_id == item.get("doc_id")), None)
        if target is not None:
            target.definition_context.append(dict(item))
    return rows


def _summary(rows):
    good = [row for row in rows if not row.get("error")]
    baseline = sum(row["judge"]["baseline"]["correct"] for row in good)
    candidate = sum(row["judge"]["candidate"]["correct"] for row in good)
    return {
        "cases": len(rows), "completed": len(good),
        "baseline_correct": baseline, "candidate_correct": candidate,
        "delta": candidate - baseline,
        "paired": {
            "both_correct": sum(row["judge"]["baseline"]["correct"]
                                and row["judge"]["candidate"]["correct"] for row in good),
            "baseline_only": sum(row["judge"]["baseline"]["correct"]
                                 and not row["judge"]["candidate"]["correct"] for row in good),
            "candidate_only": sum(not row["judge"]["baseline"]["correct"]
                                  and row["judge"]["candidate"]["correct"] for row in good),
            "both_incorrect": sum(not row["judge"]["baseline"]["correct"]
                                  and not row["judge"]["candidate"]["correct"] for row in good),
        },
        "usage": {name: {key: sum(row[name]["usage"][key] for row in good)
                         for key in ("calls", "input_tokens", "output_tokens",
                                     "duration_ms", "errors")}
                  for name in ("baseline", "candidate")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--retrieval", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0038/definition_context_wiki_51.json")
    parser.add_argument(
        "--baseline", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legalclosure_stage_answer_ab_51.json")
    parser.add_argument(
        "--stage", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legalclosure_stage_ablation_51.json")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0038/definition_only_fresh_answer_ab_27.json")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--manifest-existing", action="store_true")
    args = parser.parse_args()
    if args.manifest_existing:
        result = json.loads(args.out.read_text("utf-8"))
        digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
        artifact_dir = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0038-definition-context-wiki-hygiene/artifacts"
        manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
        manifest["definition_only_fresh_ab"] = {
            "raw_result": str(args.out.resolve().relative_to(ROOT)),
            "sha256": digest, "bytes": args.out.stat().st_size,
            "summary": result["summary"],
        }
        (artifact_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 0
    retrieval = json.loads(args.retrieval.read_text("utf-8"))
    baseline_answers = {row["case_no"]: row
                        for row in json.loads(args.baseline.read_text("utf-8"))["rows"]}
    stage = {row["case_no"]: row for row in json.loads(args.stage.read_text("utf-8"))["rows"]}
    affected = [row for row in retrieval["rows"]
                if row["candidate"]["definition_dropped"]]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU:
        raise SystemExit("Haiku model contract failed")
    index = index_mod.current().scoped(None)
    local = threading.local()

    def evaluate(source):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_no, question = source["case_no"], source["question"]
        baseline_selected = stage[case_no]["variants"]["control_d_then_verifier"]["selected"]
        candidate_selected = source["candidate"]["selected"]
        sections = {
            "baseline": _sections(index, baseline_selected),
            "candidate": _sections(index, candidate_selected,
                                   source["candidate"]["definition_appendix"]),
        }
        order = ("candidate", "baseline") if int(case_no[-3:]) % 2 == 0 \
            else ("baseline", "candidate")
        generated = {}
        for name in order:
            log0 = len(llm.log)
            started = time.perf_counter()
            result = answer.synthesize(llm, question, sections[name], spots=[])
            generated[name] = {
                "answer": result.answer, "answerable": result.answerable,
                "usage": _usage(list(llm.log)[log0:]),
                "wall_ms": round((time.perf_counter() - started) * 1000),
            }
            if result.error or not result.answer:
                raise RuntimeError(result.error or f"empty {name}")
        reference = baseline_answers[case_no]["reference_answer"]
        # 제품 호출 순서와 반대로 judge A/B를 배치한다.
        a_name, b_name = order[1], order[0]
        user = (f"[기준답변]\n{reference}\n\n[답변 A]\n{generated[a_name]['answer']}\n\n"
                f"[답변 B]\n{generated[b_name]['answer']}")
        j0 = len(llm.log)
        judged = llm.structured(
            "eval.adr0038.definition-only", JUDGE_SYSTEM, user, JUDGE_SCHEMA,
            max_tokens=1400, effort="medium", model=HAIKU)
        judge_usage = _usage(list(llm.log)[j0:])
        if judged is None:
            raise RuntimeError("judge failed")
        labels = {a_name: "A", b_name: "B"}
        normalized = {name: {"correct": bool(judged[labels[name]]["correct"]),
                             "reason": str(judged[labels[name]]["reason"])[:800]}
                      for name in ("baseline", "candidate")}
        return {
            "case_no": case_no, "question": question, "reference_answer": reference,
            "baseline": generated["baseline"], "candidate": generated["candidate"],
            "judge_order": labels, "judge": normalized, "judge_usage": judge_usage,
            "definition_removed": source["candidate"]["definition_dropped"],
            "definition_appendix": source["candidate"]["definition_appendix"],
        }

    rows, pos = [], {row["case_no"]: i for i, row in enumerate(affected)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): row["case_no"] for row in affected}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            cid = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": cid, "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda item: pos[item["case_no"]])
            mark = row.get("judge") or {}
            print(f"[{i:02d}/{len(affected)}] {cid} "
                  f"B={'○' if (mark.get('baseline') or {}).get('correct') else '✗'} "
                  f"C={'○' if (mark.get('candidate') or {}).get('correct') else '✗'}", flush=True)
    result = {"experiment": "ADR-0038-definition-only-fresh-fresh-ab",
              "model_contract": {"baseline": HAIKU, "candidate": HAIKU, "judge": HAIKU},
              "summary": _summary(rows), "rows": rows}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    artifact_dir = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0038-definition-context-wiki-hygiene/artifacts"
    manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
    manifest["definition_only_fresh_ab"] = {
        "raw_result": str(args.out.resolve().relative_to(ROOT)), "sha256": digest,
        "bytes": args.out.stat().st_size, "summary": result["summary"]}
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
