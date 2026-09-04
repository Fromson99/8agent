#!/usr/bin/env python3
"""ADR-0038: 기존 Haiku 답변과 정의/Wiki 정리 후보를 51건 Haiku paired A/B한다."""

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


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 저장소 환경 기본값
from lawrag.core.rag import answer, legal_coordinates, legalclosure  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import _percentile, _usage  # noqa: E402


HAIKU = "claude-haiku-4-5-20251001"
JUDGE_SYSTEM = (
    "너는 법률 E2E 답변의 동일 기준 비교 채점자다. 기준답변은 사람이 확정한 정답이다. "
    "답변 A와 B를 각각 독립적으로 채점한다. 핵심 결론·조건·예외·수치가 기준답변과 "
    "일치하고 중요한 누락이나 모순이 없을 때만 correct=true다. 더 자세한 관련 설명은 "
    "허용하지만 다른 규범을 지배규범처럼 섞거나 근거가 있는데도 회피하면 false다. "
    "A와 B가 같아도 각각 같은 기준으로 판정한다."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "A": {"type": "object", "properties": {
            "correct": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["correct", "reason"], "additionalProperties": False},
        "B": {"type": "object", "properties": {
            "correct": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["correct", "reason"], "additionalProperties": False},
    },
    "required": ["A", "B"], "additionalProperties": False,
}


def _sections(index, selected, question, appendix):
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


def _labels(case_no: str, baseline: str, candidate: str) -> tuple[dict, str]:
    """사례 번호 홀짝으로 A/B 순서를 교차해 고정 위치 편향을 줄인다."""
    even = int(case_no.rsplit("-", 1)[-1]) % 2 == 0
    values = {"A": candidate, "B": baseline} if even else {
        "A": baseline, "B": candidate}
    mapping = {"baseline": "B", "candidate": "A"} if even else {
        "baseline": "A", "candidate": "B"}
    user = (f"[기준답변]\n{{reference}}\n\n[답변 A]\n{values['A']}\n\n"
            f"[답변 B]\n{values['B']}")
    return mapping, user


def _summary(rows):
    good = [row for row in rows if not row.get("error")]
    baseline = sum(row["judge"]["baseline"]["correct"] for row in good)
    candidate = sum(row["judge"]["candidate"]["correct"] for row in good)
    product_ms = [row["candidate"]["product_wall_ms"] for row in good]
    return {
        "cases": len(rows), "completed": len(good),
        "baseline_correct": baseline,
        "baseline_accuracy": round(baseline / len(good), 4) if good else 0,
        "candidate_correct": candidate,
        "candidate_accuracy": round(candidate / len(good), 4) if good else 0,
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
        "candidate_product_usage": {key: sum(row["candidate"]["usage"][key]
                                               for row in good)
                                    for key in ("calls", "input_tokens", "output_tokens",
                                                "duration_ms", "errors")},
        "paired_judge_usage": {key: sum(row["judge_usage"][key] for row in good)
                               for key in ("calls", "input_tokens", "output_tokens",
                                           "duration_ms", "errors")},
        "candidate_product_wall_ms_p50": _percentile(product_ms, .5),
        "candidate_product_wall_ms_p95": _percentile(product_ms, .95),
        "candidate_product_wall_ms_mean": round(statistics.mean(product_ms), 3)
        if product_ms else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--candidate-retrieval", type=Path,
        default=ROOT / "var/eval/e2e/ADR-0038/definition_context_wiki_51.json")
    parser.add_argument(
        "--baseline-answers", type=Path,
        default=ROOT / "var/eval/e2e/cm_core_legalclosure_stage_answer_ab_51.json")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "var/eval/e2e/ADR-0038/definition_context_answer_ab_51.json")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--cases", default="")
    parser.add_argument("--manifest-existing", action="store_true")
    args = parser.parse_args()
    if args.manifest_existing:
        result = json.loads(args.out.read_text("utf-8"))
        digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
        artifact_dir = ROOT / "docs/adr/ADR-0038-definition-context-wiki-hygiene/artifacts"
        manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
        manifest["answer_ab"] = {
            "raw_result": str(args.out.resolve().relative_to(ROOT)),
            "sha256": digest, "bytes": args.out.stat().st_size,
            "summary": result["summary"],
        }
        (artifact_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 0

    candidate_blob = json.loads(args.candidate_retrieval.read_text("utf-8"))
    baseline_blob = json.loads(args.baseline_answers.read_text("utf-8"))
    baseline_by_case = {row["case_no"]: row for row in baseline_blob["rows"]}
    wanted = {item.strip() for item in args.cases.split(",") if item.strip()}
    source_rows = [row for row in candidate_blob["rows"]
                   if not wanted or row["case_no"] in wanted]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU:
        raise SystemExit(f"모든 LLM은 {HAIKU}여야 합니다: {getattr(prototype, 'model', None)}")
    index = index_mod.current().scoped(None)
    local = threading.local()

    def evaluate(source):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm is None or local.llm.model != HAIKU:
                raise RuntimeError("worker model is not Haiku")
        llm = local.llm
        case_no, question = source["case_no"], source["question"]
        baseline_row = baseline_by_case[case_no]
        baseline = baseline_row["variants"]["control_d_then_verifier"]["answer"]
        reference = baseline_row["reference_answer"]
        sections = _sections(
            index, source["candidate"]["selected"], question,
            source["candidate"].get("definition_appendix") or [])
        log0 = len(llm.log)
        started = time.perf_counter()
        generated = answer.synthesize(llm, question, sections, spots=[])
        product_ms = round((time.perf_counter() - started) * 1000)
        product_usage = _usage(list(llm.log)[log0:])
        if generated.error or not generated.answer:
            raise RuntimeError(generated.error or "empty candidate answer")

        mapping, template = _labels(case_no, baseline, generated.answer)
        judge_user = template.replace("{reference}", reference)
        judge0 = len(llm.log)
        judged = llm.structured(
            "eval.adr0038.paired", JUDGE_SYSTEM, judge_user, JUDGE_SCHEMA,
            max_tokens=1400, effort="medium", model=HAIKU)
        judge_usage = _usage(list(llm.log)[judge0:])
        if judged is None:
            raise RuntimeError("paired judge failed")
        normalized = {
            name: {"correct": bool(judged[label]["correct"]),
                   "reason": str(judged[label]["reason"])[:800]}
            for name, label in mapping.items()
        }
        return {
            "case_no": case_no, "question": question, "reference_answer": reference,
            "baseline": {"answer": baseline},
            "candidate": {
                "answer": generated.answer, "answerable": generated.answerable,
                "selected_count": len(sections),
                "definition_entries": sum(len(row.definition_context) for row in sections),
                "wiki": generated.wiki, "usage": product_usage,
                "product_wall_ms": product_ms,
            },
            "judge_order": mapping, "judge": normalized, "judge_usage": judge_usage,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows, order = [], {row["case_no"]: i for i, row in enumerate(source_rows)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): row["case_no"] for row in source_rows}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_no = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_no,
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda item: order[item["case_no"]])
            result = {
                "experiment": "ADR-0038-definition-context-answer-ab-v1",
                "model_contract": {"product": HAIKU, "judge": HAIKU,
                                   "baseline_answer_model": baseline_blob["system_model"]},
                "sources": {"candidate_retrieval": str(args.candidate_retrieval),
                            "baseline_answers": str(args.baseline_answers)},
                "summary": _summary(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
            mark = row.get("judge") or {}
            print(f"[{position:02d}/{len(source_rows)}] {case_no} "
                  f"B={'○' if (mark.get('baseline') or {}).get('correct') else '✗'} "
                  f"C={'○' if (mark.get('candidate') or {}).get('correct') else '✗'}",
                  flush=True)

    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    artifact_dir = ROOT / "docs/adr/ADR-0038-definition-context-wiki-hygiene/artifacts"
    manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
    manifest["answer_ab"] = {
        "raw_result": str(args.out.resolve().relative_to(ROOT)), "sha256": digest,
        "bytes": args.out.stat().st_size, "summary": _summary(rows),
    }
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
