#!/usr/bin/env python3
"""골든-only 법률효과 컴파일·결정론 실행기 5건 shadow 실험."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.research.experiments.haiku_legal_effect_executor import (  # noqa: E402
    COMPILER_SCHEMA, COMPILER_SYSTEM, HAIKU_MODEL, compiler_user,
    execute_compilation, validate_compilation,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_export_wrong_final_prompt_io import _fence, _json_fence  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import _usage  # noqa: E402


CASES = (
    {
        "id": "cm-003", "number": 1, "task_kind": "EXCEPTION_SWITCH",
        "title": "제3호 예외에서 제4호로 전환",
        "contract": (
            "질문의 두 후보 규정 중 본문상 최초 후보, 그 후보의 세칙상 예외, 예외가 "
            "질문 속 행위자에게 충족되는지, 충족 시 적용되는 대체 후보를 rule과 "
            "EXCEPTION_SWITCH decision으로 만든다. result에는 적용되는 호를 명시한다."
        ),
    },
    {
        "id": "cm-002", "number": 2, "task_kind": "SLOT_COVERAGE",
        "title": "하나의 호 안의 서로 다른 두 기준일",
        "contract": (
            "제4호 문장 안에서 서로 다른 계산 대상에 붙은 모든 기준일을 각각 독립 "
            "answer_slot으로 만든다. label은 무엇의 기준일인지, value는 해당 기준일을 "
            "명시한다. 단수 질문이라는 이유로 하나만 고르지 않는다."
        ),
    },
    {
        "id": "cm-030", "number": 3, "task_kind": "APPLICABILITY_GATE",
        "title": "분기보고서 첨부의무의 적용대상 범위",
        "contract": (
            "1분기 검토보고서 조항의 적용대상을 SCOPE rule로 만들고, 질문의 상장 전 "
            "발행인이 그 적용대상에 포함되는지 APPLICABILITY_GATE decision으로 판정한다. "
            "IPO에 별도로 적용되는 반기재무제표 조건은 answer_slot으로 분리한다."
        ),
    },
    {
        "id": "cm-051", "number": 4, "task_kind": "SLOT_COVERAGE",
        "title": "일반 산정식과 조합 간주·제외의 완전성",
        "contract": (
            "보유비율 산정에 필요한 일반 준용 규칙, 조합·집합투자기구의 간주 보유, "
            "보유에서 제외하는 규칙을 각각 answer_slot으로 만든다. 질문의 핵심 산정 "
            "방법을 구성하는 항을 누락하지 않는다."
        ),
    },
    {
        "id": "cm-041", "number": 5, "task_kind": "RULE_WITH_EXCEPTION",
        "title": "이사 수 원칙과 자본금 예외 정답 보존 control",
        "contract": (
            "이사 최소 인원 원칙과 자본금 기준 예외를 별도 rule·answer_slot으로 만든다. "
            "상장 여부 자체가 원문의 인원 기준인지도 원문 범위 안에서 unresolved 또는 "
            "slot으로 표시한다. 원칙만 말하고 예외를 누락하지 않는다."
        ),
    },
)


def _dump(ex) -> dict:
    value = ex.dump()
    value["parsed"] = ex.parsed
    return value


def _grade_with_log(llm, case: dict, answer: str, evidence: list[dict]) -> dict:
    log0 = len(llm.log)
    correct, grade, votes, usage = _grade(llm, case, answer, 3, evidence)
    return {"correct": bool(correct), "grade": grade, "votes": votes,
            "usage": usage, "raw_exchanges": [_dump(ex) for ex in llm.log[log0:]]}


def _summary(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    baseline = sum(bool(row["baseline_grade"]["correct"]) for row in good)
    compiled = sum(bool(row["compiled_grade"]["correct"]) for row in good)
    guarded = sum(bool(row["guarded_grade"]["correct"]) for row in good)
    return {
        "cases": len(rows), "completed": len(good),
        "baseline_correct": baseline,
        "compiled_correct": compiled,
        "delta": compiled - baseline,
        "guarded_correct": guarded,
        "guarded_delta": guarded - baseline,
        "guarded_candidate_only_correct": sum(
            not row["baseline_grade"]["correct"] and row["guarded_grade"]["correct"]
            for row in good),
        "guarded_baseline_only_correct": sum(
            row["baseline_grade"]["correct"] and not row["guarded_grade"]["correct"]
            for row in good),
        "guarded_both_correct": sum(
            row["baseline_grade"]["correct"] and row["guarded_grade"]["correct"]
            for row in good),
        "guarded_both_wrong": sum(
            not row["baseline_grade"]["correct"] and not row["guarded_grade"]["correct"]
            for row in good),
        "candidate_only_correct": sum(
            not row["baseline_grade"]["correct"] and row["compiled_grade"]["correct"]
            for row in good),
        "baseline_only_correct": sum(
            row["baseline_grade"]["correct"] and not row["compiled_grade"]["correct"]
            for row in good),
        "both_correct": sum(
            row["baseline_grade"]["correct"] and row["compiled_grade"]["correct"]
            for row in good),
        "both_wrong": sum(
            not row["baseline_grade"]["correct"] and not row["compiled_grade"]["correct"]
            for row in good),
        "executable": sum(bool(row["execution"]["answerable"]) for row in good),
        "guarded_executable": sum(bool(row["guarded_execution"]["answerable"])
                                  for row in good),
        "compiler_usage": {name: sum(int(row["compiler_usage"].get(name, 0))
                                        for row in good)
                           for name in ("calls", "input_tokens", "output_tokens",
                                        "duration_ms", "errors")},
        "grade_usage": {name: sum(int(grade["usage"].get(name, 0))
                                     for row in good
                                     for grade in (row["baseline_grade"],
                                                   row["compiled_grade"],
                                                   row["guarded_grade"]))
                        for name in ("calls", "input_tokens", "output_tokens",
                                     "duration_ms", "errors")},
    }


def _case_markdown(row: dict) -> str:
    request = row["compiler_request"]
    base = row["baseline_product"]
    lines = [
        f"# 질문 {row['number']} — {row['case_no']} — {row['title']}", "",
        "> 이 파일은 실제 shadow 실행의 prompt와 출력을 생략 없이 보존한다. 모든 LLM",
        f"> 호출은 `{HAIKU_MODEL}`이다. 기준답변은 제품·컴파일러 prompt에 넣지 않고",
        "> 의미 채점에만 사용했다.", "",
        "## 1. 실제 사용자 질문", "", _fence(row["question"]), "",
        "## 2. 기준답변 — 제품·컴파일러에는 비공개", "",
        _fence(row["reference_answer"]), "",
        "## 3. 실험 계약", "",
        f"- task kind: `{row['task_kind']}`",
        f"- task contract: {row['task_contract']}",
        "- 골든 조문만 사용", "- 최종 답변 생성 LLM 없음: 검증된 구조를 코드가 렌더링", "",
        "## 4. 골든 원문 — 전체", "", _json_fence(row["gold_evidence"]), "",
        "## 5. 대조군: 기존 gold-only 최종 제품 입력 system", "",
        _fence(base["request"]["system"]), "",
        "## 6. 대조군: 기존 gold-only 최종 제품 입력 user — 전체", "",
        _fence(base["request"]["user"]), "",
        "## 7. 대조군: 기존 gold-only structured output", "",
        _json_fence(base["output"]), "",
        "## 8. 대조군: provider 원응답", "", _json_fence(base["raw_exchanges"]), "",
        "## 9. Haiku 법률효과 컴파일 입력 system", "",
        _fence(request["system"]), "",
        "## 10. Haiku 법률효과 컴파일 입력 user — 전체", "",
        _fence(request["user"]), "",
        "## 11. Haiku 법률효과 컴파일 schema", "",
        _json_fence(request["schema"]), "",
        "## 12. Haiku 법률효과 컴파일 structured output", "",
        _json_fence(row["compiler_output"]), "",
        "## 13. 컴파일 provider 원응답", "",
        _json_fence(row["compiler_raw_exchanges"]), "",
        "## 14. 결정론 원문-span 검증 결과", "", _json_fence(row["validation"]), "",
        "## 15. 결정론 실행 trace", "", _json_fence(row["execution"]["trace"]), "",
        "## 16. strict 결정론 최종 답변", "", _fence(row["execution"]["answer"]), "",
        "## 17. guarded 결정론 실행 trace", "",
        _json_fence(row["guarded_execution"]["trace"]), "",
        "## 18. guarded 결정론 최종 답변", "",
        _fence(row["guarded_execution"]["answer"]), "",
        "## 19. 대조군 Haiku 3표결", "", _json_fence(row["baseline_grade"]), "",
        "## 20. strict 컴파일 답변 Haiku 3표결", "", _json_fence(row["compiled_grade"]), "",
        "## 21. guarded 컴파일 답변 Haiku 3표결", "", _json_fence(row["guarded_grade"]), "",
        "## 22. 판정 요약", "",
        f"- 대조군 정답: `{row['baseline_grade']['correct']}`",
        f"- strict 컴파일 답변 정답: `{row['compiled_grade']['correct']}`",
        f"- guarded 컴파일 답변 정답: `{row['guarded_grade']['correct']}`",
        f"- strict/guarded 실행 가능: `{row['execution']['answerable']}` / "
        f"`{row['guarded_execution']['answerable']}`", "",
    ]
    return "\n".join(lines)


def _index_markdown(result: dict) -> str:
    s = result["summary"]
    lines = [
        "# 골든-only 법률효과 실행기 — 질문별 실제 prompt/output", "",
        "각 파일은 실제 질문, 골든 원문, 기존 답변 prompt/output, Haiku 컴파일",
        "prompt/output, 결정론 검증·실행, 두 답변의 Haiku 3표결을 포함한다.", "",
        "| 번호 | 사례 | 연산 | 대조군 | strict | guarded | strict/guarded 실행 | 파일 |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for row in result["rows"]:
        if row.get("error"):
            lines.append(f"| {row['number']} | {row['case_no']} | ERROR | - | - | - | - |")
            continue
        filename = row["markdown_file"]
        lines.append(
            f"| {row['number']} | {row['case_no']} | `{row['task_kind']}` | "
            f"{'○' if row['baseline_grade']['correct'] else '✗'} | "
            f"{'○' if row['compiled_grade']['correct'] else '✗'} | "
            f"{'○' if row['guarded_grade']['correct'] else '✗'} | "
            f"{'○' if row['execution']['answerable'] else '✗'} / "
            f"{'○' if row['guarded_execution']['answerable'] else '✗'} | "
            f"[{filename}]({filename}) |"
        )
    lines += [
        "", "## 집계", "",
        f"- 대조군: **{s['baseline_correct']}/{s['completed']}**",
        f"- 컴파일+결정론 실행: **{s['compiled_correct']}/{s['completed']}**",
        f"- 순증: **{s['delta']:+d}건**",
        f"- guarded 컴파일+결정론 실행: **{s['guarded_correct']}/{s['completed']}**",
        f"- guarded 순증: **{s['guarded_delta']:+d}건**",
        f"- strict 신규 정답/회귀: **{s['candidate_only_correct']}/{s['baseline_only_correct']}**",
        f"- guarded 신규 정답/회귀: "
        f"**{s['guarded_candidate_only_correct']}/{s['guarded_baseline_only_correct']}**",
        "", "이 5건은 기존 오류를 보고 선택한 인샘플 방법론 probe이므로 일반화 성능이 아니다.", "",
    ]
    return "\n".join(lines)


def _persist(result: dict, out: Path, experiment_dir: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    for row in result["rows"]:
        if not row.get("error"):
            (experiment_dir / row["markdown_file"]).write_text(_case_markdown(row), "utf-8")
    (experiment_dir / "README.md").write_text(_index_markdown(result), "utf-8")
    question_files = []
    for path in sorted(experiment_dir.glob("질문-*.md")):
        question_files.append({
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    (experiment_dir / "manifest.json").write_text(json.dumps({
        "artifact": str(out),
        "question_files": question_files,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    suite = {str(row["id"]): row for row in
             json.loads(args.suite.read_text("utf-8")).get("cases") or []}
    source_blob = json.loads(args.source_run.read_text("utf-8"))
    source = {str(row["case_no"]): row for row in source_blob.get("rows") or []}
    local = threading.local()

    def evaluate(config: dict) -> dict:
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm.backend == "anthropic":
                local.llm.model = HAIKU_MODEL
        llm = local.llm
        case_id = config["id"]
        case = suite[case_id]
        source_row = source[case_id]
        baseline = source_row["variants"]["gold_only"]
        evidence = copy.deepcopy(source_row["gold_evidence"])
        request = {
            "call_name": "eval.legal_effect.compile.haiku",
            "system": COMPILER_SYSTEM,
            "user": compiler_user(case["question"], evidence, config["task_kind"],
                                  config["contract"]),
            "schema": COMPILER_SCHEMA,
            "max_tokens": 7000, "effort": "low",
        }
        log0 = len(llm.log)
        started = time.perf_counter()
        output = llm.structured(
            request["call_name"], request["system"], request["user"], request["schema"],
            max_tokens=request["max_tokens"], effort=request["effort"], model=HAIKU_MODEL)
        wall_ms = round((time.perf_counter() - started) * 1000)
        exchanges = list(llm.log)[log0:]
        if output is None:
            raise RuntimeError(exchanges[-1].error if exchanges else "empty compiler output")
        validation = validate_compilation(output, evidence, config["task_kind"])
        execution = execute_compilation(validation)
        guarded_execution = execute_compilation(validation, allow_unresolved=True)
        baseline_answer = str(baseline["output"].get("answer") or "")
        baseline_grade = _grade_with_log(llm, case, baseline_answer, evidence)
        compiled_grade = _grade_with_log(llm, case, execution["answer"], evidence)
        guarded_grade = _grade_with_log(llm, case, guarded_execution["answer"], evidence)
        filename = f"질문-{config['number']:02d}-{case_id}.md"
        return {
            "number": config["number"], "case_no": case_id, "title": config["title"],
            "task_kind": config["task_kind"], "task_contract": config["contract"],
            "question": case["question"], "reference_answer": case["reference_answer"],
            "gold_evidence": evidence,
            "baseline_product": {"request": baseline["request"],
                                 "output": baseline["output"],
                                 "raw_exchanges": baseline["raw_exchanges"]},
            "compiler_request": request, "compiler_output": output,
            "compiler_raw_exchanges": [_dump(ex) for ex in exchanges],
            "compiler_usage": _usage(exchanges), "compiler_wall_ms": wall_ms,
            "validation": validation, "execution": execution,
            "guarded_execution": guarded_execution,
            "baseline_grade": baseline_grade, "compiled_grade": compiled_grade,
            "guarded_grade": guarded_grade,
            "markdown_file": filename,
        }

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, config): config for config in CASES}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            config = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"number": config["number"], "case_no": config["id"],
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: int(value["number"]))
            result = {
                "experiment": "haiku-gold-only-source-span-legal-effect-executor-probe5-v2",
                "contract": {"main_wiring_changed": False, "gold_only": True,
                             "reference_visible_to_compiler": False,
                             "all_llm_calls": HAIKU_MODEL,
                             "final_answer_generated_by_llm": False,
                             "exact_source_span_validation": True,
                             "diagnostic_in_sample": True},
                "sources": {"suite": str(args.suite), "source_run": str(args.source_run)},
                "summary": _summary(rows), "rows": rows,
            }
            _persist(result, args.out, args.experiment_dir)
            if row.get("error"):
                print(f"[{position}/5] {config['id']} ERROR {row['error']}", flush=True)
            else:
                print(f"[{position}/5] {config['id']} "
                      f"base={'○' if row['baseline_grade']['correct'] else '✗'} "
                      f"compiled={'○' if row['compiled_grade']['correct'] else '✗'} "
                      f"guarded={'○' if row['guarded_grade']['correct'] else '✗'} "
                      f"exec={'○' if row['execution']['answerable'] else '✗'}/"
                      f"{'○' if row['guarded_execution']['answerable'] else '✗'}", flush=True)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
