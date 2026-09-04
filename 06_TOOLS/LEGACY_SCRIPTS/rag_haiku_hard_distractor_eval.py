#!/usr/bin/env python3
"""정답 조문을 고정하고 법률형 방해근거만 바꾸는 Haiku shadow 실험."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import threading
import time
from typing import Any


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag.experiments.haiku_hard_distractors import (  # noqa: E402
    CLASSIFIER_SYSTEM, HAIKU_MODEL, VARIANTS, build_variants,
    classifier_schema, classifier_user, deterministic_random_ids,
    normalize_labels,
)
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import (  # noqa: E402
    SEMANTIC_SCHEMA, SEMANTIC_SYSTEM, _coords, _expected_article_coords,
)
from scripts.rag_export_wrong_final_prompt_io import (  # noqa: E402
    _fence, _json_fence, build_product_request, sha256_text,
)
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import _percentile, _usage  # noqa: E402


GRADE_SYSTEM = (
    SEMANTIC_SYSTEM
    + " 채점 순서: (1) 기준답변을 최소 필수명제로 분해하고, (2) 시스템 답변이 "
      "각 명제를 지지하는지 확인하고, (3) 반대 결론이나 중요한 수치·조건·예외 "
      "오류가 있는지 확인한다. 기준답변보다 상세하다는 이유만으로 감점하지 마라. "
      "모든 판정은 제공된 질문·기준답변·시스템 답변만으로 한다."
)


def _exchange(ex) -> dict[str, Any]:
    value = ex.dump()
    value["parsed"] = ex.parsed
    return value


def _request_hashes(request: dict) -> dict:
    return {
        "system_sha256": sha256_text(str(request["system"])),
        "user_sha256": sha256_text(str(request["user"])),
        "schema_sha256": hashlib.sha256(json.dumps(
            request["schema"], ensure_ascii=False, sort_keys=True
        ).encode("utf-8")).hexdigest(),
    }


def _gold_rows(case: dict, evidence: list[dict]) -> list[dict]:
    expected = _expected_article_coords(case)
    rows = []
    for row in evidence:
        if _coords(_sections([row])) & expected:
            rows.append(row)
    return rows


def _renumber(rows: list[dict]) -> list[dict]:
    out = []
    for position, row in enumerate(rows, 1):
        value = copy.deepcopy(row)
        value["presented_id"] = f"E{position}"
        out.append(value)
    return out


def _evidence_signature(rows: list[dict]) -> list[tuple]:
    return [(row.get("doc_id"), row.get("node"), row.get("source_case"),
             row.get("source_evidence_id")) for row in rows]


def _call_product(llm, question: str, evidence: list[dict]) -> dict:
    sections = _sections(evidence)
    request = build_product_request(question, sections, spots=[])
    log0 = len(llm.log)
    started = time.perf_counter()
    output = llm.structured(
        request["call_name"], request["system"], request["user"], request["schema"],
        max_tokens=request["max_tokens"], effort=request["effort"], model=HAIKU_MODEL,
    )
    wall_ms = round((time.perf_counter() - started) * 1000)
    exchanges = list(llm.log)[log0:]
    return {
        "request": request,
        "request_hashes": _request_hashes(request),
        "output": dict(output or {}),
        "raw_exchanges": [_exchange(ex) for ex in exchanges],
        "usage": _usage(exchanges),
        "wall_ms": wall_ms,
        "error": "" if output is not None else (
            str(exchanges[-1].error) if exchanges else "empty product output"),
    }


def _grade_request(case: dict, answer: str) -> dict:
    user = (
        f"[질문]\n{case['question']}\n\n"
        f"[기준답변]\n{case.get('reference_answer', '')}\n\n"
        f"[시스템 답변]\n{answer[:8000]}\n\n"
        "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다."
    )
    return {
        "call_name": "eval.answer.semantic.hard_distractor",
        "system": GRADE_SYSTEM,
        "user": user,
        "schema": SEMANTIC_SCHEMA,
        "max_tokens": 1600,
        "effort": "low",
    }


def _grade(llm, case: dict, answer: str, repeats: int) -> dict:
    request = _grade_request(case, answer)
    votes, exchanges, usages = [], [], []
    for _ in range(repeats):
        log0 = len(llm.log)
        output = llm.structured(
            request["call_name"], request["system"], request["user"], request["schema"],
            max_tokens=request["max_tokens"], effort=request["effort"], model=HAIKU_MODEL,
        )
        called = list(llm.log)[log0:]
        votes.append(dict(output or {}))
        exchanges.extend(_exchange(ex) for ex in called)
        usages.append(_usage(called))
    yes = sum(bool(vote.get("correct")) for vote in votes)
    correct = yes > repeats // 2
    representative = next(
        (vote for vote in votes if bool(vote.get("correct")) == correct), votes[0] or {})
    names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors",
             "truncated_calls")
    usage = {name: sum(int(row.get(name, 0)) for row in usages) for name in names}
    return {
        "request": request,
        "request_hashes": _request_hashes(request),
        "correct": correct,
        "representative": representative,
        "votes": votes,
        "raw_exchanges": exchanges,
        "usage": usage,
    }


def _sum_variant_usage(rows: list[dict], variant: str, field: str) -> dict:
    names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    return {
        name: sum(int(((((row.get("variants") or {}).get(variant) or {}).get(field)
                        or {}).get(name, 0))) for row in rows
                  if not (((row.get("variants") or {}).get(variant) or {})
                          .get("reused_from")))
        for name in names
    }


def _summary(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    out: dict[str, Any] = {"cases": len(rows), "completed": len(good), "variants": {}}
    gold_map = {
        row["case_no"]: bool(row["variants"]["gold_only"]["grade"]["correct"])
        for row in good
    }
    for variant in VARIANTS:
        values = [row["variants"][variant] for row in good]
        applicable = [
            (row, row["variants"][variant]) for row in good
            if variant in ("gold_only", "full_original")
            or int(row["variants"][variant].get("injected_count") or 0) > 0
        ]
        correct = sum(bool(value["grade"]["correct"]) for value in values)
        paired = {"both_correct": 0, "gold_only_correct": 0,
                  "variant_only_correct": 0, "both_wrong": 0}
        for row, value in applicable:
            before = gold_map[row["case_no"]]
            after = bool(value["grade"]["correct"])
            key = ("both_correct" if before and after else
                   "gold_only_correct" if before else
                   "variant_only_correct" if after else "both_wrong")
            paired[key] += 1
        denom = paired["both_correct"] + paired["gold_only_correct"]
        walls = [int(value.get("wall_ms") or 0) for value in values
                 if not value.get("reused_from")]
        out["variants"][variant] = {
            "cases": len(values),
            "applicable_cases": len(applicable),
            "semantic_correct": correct,
            "semantic_accuracy": round(correct / len(values), 4) if values else 0,
            "paired_vs_gold_only_on_applicable": paired,
            "distractor_harm_rate_given_gold_correct": round(
                paired["gold_only_correct"] / denom, 4) if denom else None,
            "product_cost": _sum_variant_usage(good, variant, "usage"),
            "grade_cost": _sum_variant_usage(good, variant, "grade_usage"),
            "wall_ms_p50": _percentile(walls, .5) if walls else 0,
            "wall_ms_p95": _percentile(walls, .95) if walls else 0,
        }
    gold_correct = out["variants"]["gold_only"]["semantic_correct"]
    full_correct = out["variants"]["full_original"]["semantic_correct"]
    out["diagnosis"] = {
        "gold_only_correct": gold_correct,
        "gold_only_wrong_interpretation_failures": len(good) - gold_correct,
        "fresh_full_correct": full_correct,
        "gold_correct_full_wrong_pruning_addressable": sum(
            gold_map[row["case_no"]]
            and not bool(row["variants"]["full_original"]["grade"]["correct"])
            for row in good),
        "gold_wrong_full_wrong_not_fixed_by_pruning": sum(
            not gold_map[row["case_no"]]
            and not bool(row["variants"]["full_original"]["grade"]["correct"])
            for row in good),
        "hard_cases_available": sum(
            int(row["variants"]["hard_after"].get("injected_count") or 0) > 0
            for row in good),
        "supportive_cases_available": sum(
            int(row["variants"]["supportive_after"].get("injected_count") or 0) > 0
            for row in good),
    }
    return out


def _case_markdown(row: dict) -> str:
    classifier = row["classifier"]
    lines = [
        f"# {row['case_no']} — hard-distractor prompt 입출력",
        "",
        "> 모든 LLM 호출은 `claude-haiku-4-5-20251001`이다. 기준답변은 제품",
        "> 답변 prompt에 들어가지 않고 의미 채점에만 사용했다. 메인 배선은 변경하지 않았다.",
        "",
        "## 질문", "", _fence(row["question"]), "",
        "## 기준답변 — 제품 prompt 비공개", "", _fence(row["reference_answer"]), "",
        "## 골든 직접근거 좌표", "", _json_fence(row["gold_evidence"]), "",
        "## Haiku 방해근거 분류 입력: system", "", _fence(classifier["request"]["system"]), "",
        "## Haiku 방해근거 분류 입력: user — 생략 없음", "",
        _fence(classifier["request"]["user"]), "",
        "## Haiku 방해근거 분류 출력", "", _json_fence(classifier["output"]), "",
        "## 정규화된 역할", "", _json_fence(classifier["labels"]), "",
    ]
    for variant in VARIANTS:
        value = row["variants"][variant]
        lines += [
            f"## 변형 `{variant}`", "",
            f"- 추가 근거: `{value['injected_count']}개`",
            f"- 의미 정답: `{value['grade']['correct']}`",
            f"- 재사용: `{value.get('reused_from') or '없음'}`", "",
            "### 제시 근거 좌표와 원문", "", _json_fence(value["evidence"]), "",
            "### 최종 제품 입력: system", "", _fence(value["request"]["system"]), "",
            "### 최종 제품 입력: user — 전체 원문, 생략 없음", "",
            _fence(value["request"]["user"]), "",
            "### 최종 제품 입력: schema", "", _json_fence(value["request"]["schema"]), "",
            "### 제품 structured output", "", _json_fence(value["output"]), "",
            "### 제품 원 provider 응답/로그", "", _json_fence(value["raw_exchanges"]), "",
            "### 의미 채점 입력: system", "", _fence(value["grade"]["request"]["system"]), "",
            "### 의미 채점 입력: user", "", _fence(value["grade"]["request"]["user"]), "",
            "### 의미 채점 출력", "", _json_fence(value["grade"]["votes"]), "",
            "### 의미 채점 원 provider 응답/로그", "",
            _json_fence(value["grade"]["raw_exchanges"]), "",
        ]
    return "\n".join(lines)


def _index_markdown(result: dict, json_out: Path) -> str:
    summary = result["summary"]
    lines = [
        "# CM Core 오답 16건 — Haiku hard-distractor 내성 실험",
        "",
        "정답 조문 좌표를 고정하고 추가 문맥의 종류와 위치만 바꾼 shadow 진단이다.",
        "같은 51건에서 이미 확인한 오답 16건이므로 일반화 성능이 아니라 원인 분해로 읽는다.",
        "",
        "## 실행 계약", "",
        f"- 제품·분류·채점 모델: `{HAIKU_MODEL}` only",
        "- 메인 배선 변경: 없음",
        "- 제품 prompt의 골든/기준답변 노출: 없음",
        f"- 전체 기계 원장: `{json_out}`", "",
        "## 결과", "",
        "| 변형 | 정답/전체 | 적용 가능 | gold 정답 중 오답 전환율 |",
        "|---|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        value = summary["variants"][variant]
        rate = value["distractor_harm_rate_given_gold_correct"]
        rate_text = "-" if rate is None else f"{rate:.1%}"
        lines.append(
            f"| `{variant}` | {value['semantic_correct']}/{value['cases']} | "
            f"{value['applicable_cases']} | {rate_text} |"
        )
    d = summary["diagnosis"]
    lines += [
        "", "## 원인 분해", "",
        f"- 골든 조문만으로 정답: **{d['gold_only_correct']}/{summary['completed']}**",
        f"- 골든 조문만으로도 오답(가지치기로 해결 불가): "
        f"**{d['gold_only_wrong_interpretation_failures']}건**",
        f"- 골든은 정답이나 전체 문맥에서 오답(가지치기 가능 후보): "
        f"**{d['gold_correct_full_wrong_pruning_addressable']}건**",
        f"- Haiku가 hard distractor를 찾은 사례: **{d['hard_cases_available']}건**",
        f"- Haiku가 보조근거를 찾은 사례: **{d['supportive_cases_available']}건**",
        "", "## 사례별 원문", "",
        "| 사례 | 질문 | gold | hard 뒤 | hard 앞 | 전체 | 파일 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in result["rows"]:
        if row.get("error"):
            lines.append(f"| {row['case_no']} | ERROR: {row['error']} | - | - | - | - | - |")
            continue
        marks = {variant: ("○" if row["variants"][variant]["grade"]["correct"] else "✗")
                 for variant in VARIANTS}
        question = " ".join(row["question"].split())
        if len(question) > 70:
            question = question[:67] + "…"
        lines.append(
            f"| {row['case_no']} | {question} | {marks['gold_only']} | "
            f"{marks['hard_after']} | {marks['hard_before']} | "
            f"{marks['full_original']} | [{row['case_no']}.md]({row['case_no']}.md) |"
        )
    lines += [
        "", "각 사례 파일은 분류 prompt·출력, 모든 제품 prompt·원 출력, 의미 채점",
        "prompt·원 출력을 생략 없이 포함한다.", "",
    ]
    return "\n".join(lines)


def _write_artifacts(result: dict, json_out: Path, markdown_dir: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_dir.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    for row in result["rows"]:
        if not row.get("error"):
            (markdown_dir / f"{row['case_no']}.md").write_text(
                _case_markdown(row), "utf-8")
    (markdown_dir / "README.md").write_text(_index_markdown(result, json_out), "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--wrong-prompt-io", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown-dir", type=Path, required=True)
    parser.add_argument("--cases", default="")
    parser.add_argument("--hard-limit", type=int, default=3)
    parser.add_argument("--random-pool", type=int, default=8)
    parser.add_argument("--grade-repeats", type=int, choices=(1, 3), default=1)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    suite_blob = json.loads(args.suite.read_text("utf-8"))
    wrong_blob = json.loads(args.wrong_prompt_io.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite_blob.get("cases") or []}
    sources = {str(row["case_no"]): row for row in wrong_blob.get("rows") or []}
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    case_ids = [case_id for case_id in sources if not wanted or case_id in wanted]

    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    if prototype.backend == "anthropic" and prototype.model != HAIKU_MODEL:
        prototype.model = HAIKU_MODEL

    gold_pool = []
    for case_id in case_ids:
        evidence = copy.deepcopy(sources[case_id]["reconstructed_evidence"])
        for position, row in enumerate(evidence, 1):
            row["experiment_order"] = position
        for row in _gold_rows(cases[case_id], evidence):
            value = copy.deepcopy(row)
            value["pool_id"] = f"{case_id}:{row['id']}"
            value["source_case"] = case_id
            value["source_evidence_id"] = row["id"]
            gold_pool.append(value)

    existing = {}
    if args.resume and args.out.is_file():
        previous = json.loads(args.out.read_text("utf-8"))
        existing = {str(row["case_no"]): row for row in previous.get("rows") or []
                    if not row.get("error")}
    local = threading.local()

    def evaluate(case_id: str) -> dict:
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm.backend == "anthropic":
                local.llm.model = HAIKU_MODEL
        llm = local.llm
        case = cases[case_id]
        evidence = copy.deepcopy(sources[case_id]["reconstructed_evidence"])
        for position, row in enumerate(evidence, 1):
            row["experiment_order"] = position
            row["experiment_source"] = "SAME_RETRIEVAL"
        gold = _gold_rows(case, evidence)
        if not gold:
            raise RuntimeError("골든 조문 좌표가 동결 최종 문맥에 없음")
        gold_keys = {(row.get("doc_id"), row.get("node")) for row in gold}
        candidates = [row for row in evidence
                      if (row.get("doc_id"), row.get("node")) not in gold_keys]

        other_pool = [row for row in gold_pool if row["source_case"] != case_id]
        pool_ids = deterministic_random_ids(case_id, other_pool, args.random_pool)
        by_pool_id = {str(row["pool_id"]): row for row in other_pool}
        random_controls = []
        for position, pool_id in enumerate(pool_ids, 1):
            value = copy.deepcopy(by_pool_id[pool_id])
            value["id"] = f"X{position}"
            value["experiment_source"] = "CROSS_CASE_RANDOM"
            random_controls.append(value)

        classify_candidates = candidates + random_controls
        classifier_request = {
            "call_name": "eval.rag.hard_distractor.classify",
            "system": CLASSIFIER_SYSTEM,
            "user": classifier_user(case["question"], gold, classify_candidates),
            "schema": classifier_schema([row["id"] for row in classify_candidates]),
            "max_tokens": 8000,
            "effort": "low",
        }
        log0 = len(llm.log)
        classifier_output = llm.structured(
            classifier_request["call_name"], classifier_request["system"],
            classifier_request["user"], classifier_request["schema"],
            max_tokens=classifier_request["max_tokens"],
            effort=classifier_request["effort"], model=HAIKU_MODEL,
        )
        classifier_exchanges = list(llm.log)[log0:]
        if classifier_output is None:
            raise RuntimeError("Haiku distractor 분류 실패: " + (
                classifier_exchanges[-1].error if classifier_exchanges else "empty"))
        all_labels = normalize_labels(classify_candidates, classifier_output)
        same_ids = {str(row["id"]) for row in candidates}
        random_ids = {str(row["id"]) for row in random_controls}
        same_labels = [row for row in all_labels if row["id"] in same_ids]
        random_labels = [row for row in all_labels if row["id"] in random_ids]
        random_by_id = {str(row["id"]): row for row in random_controls}
        easy_random = [row for row in random_labels if row["label"] == "EASY_IRRELEVANT"]
        easy_random.sort(key=lambda row: (int(row.get("risk") or 0), row["id"]))
        chosen_random = [random_by_id[row["id"]] for row in easy_random[:args.hard_limit]]
        if len(chosen_random) < args.hard_limit:
            used = {row["id"] for row in chosen_random}
            chosen_random += [row for row in random_controls if row["id"] not in used][
                :args.hard_limit - len(chosen_random)]

        variant_evidence = build_variants(
            gold, candidates, same_labels, chosen_random, limit=args.hard_limit)
        variant_rows: dict[str, dict] = {}
        signature_cache: dict[tuple, str] = {}
        for variant in VARIANTS:
            presented = _renumber(variant_evidence[variant])
            signature = tuple(_evidence_signature(presented))
            reused_from = signature_cache.get(signature)
            if reused_from:
                original = variant_rows[reused_from]
                product = {key: copy.deepcopy(original[key]) for key in (
                    "request", "request_hashes", "output", "raw_exchanges", "usage",
                    "wall_ms", "error")}
                grade = copy.deepcopy(original["grade"])
            else:
                product = _call_product(llm, case["question"], presented)
                if product["error"]:
                    raise RuntimeError(f"{variant} product: {product['error']}")
                answer = str(product["output"].get("answer") or "")
                grade = _grade(llm, case, answer, args.grade_repeats)
                signature_cache[signature] = variant
            injected = max(0, len(presented) - len(gold))
            variant_rows[variant] = {
                "evidence": presented,
                "evidence_signature": [list(value) for value in signature],
                "injected_count": injected,
                "reused_from": reused_from,
                **product,
                "grade": grade,
                "grade_usage": grade["usage"],
            }
        return {
            "case_no": case_id,
            "question": case["question"],
            "reference_answer": case.get("reference_answer") or "",
            "gold_evidence": _renumber(gold),
            "classifier": {
                "request": classifier_request,
                "request_hashes": _request_hashes(classifier_request),
                "output": classifier_output,
                "labels": all_labels,
                "raw_exchanges": [_exchange(ex) for ex in classifier_exchanges],
                "usage": _usage(classifier_exchanges),
            },
            "variants": variant_rows,
        }

    rows = list(existing.values())
    pending = [case_id for case_id in case_ids if case_id not in existing]
    order = {case_id: position for position, case_id in enumerate(case_ids)}

    def persist() -> dict:
        rows.sort(key=lambda row: order[row["case_no"]])
        result = {
            "experiment": "haiku-hard-distractor-robustness-wrong16-shadow-v1",
            "contract": {
                "main_wiring_changed": False,
                "diagnostic_in_sample_wrong_cases": True,
                "retrieval_frozen": True,
                "gold_coordinates_used_only_to_construct_control": True,
                "reference_answer_visible_to_product": False,
                "all_llm_calls_model": HAIKU_MODEL,
                "classifier_model": HAIKU_MODEL,
                "answer_model": HAIKU_MODEL,
                "semantic_evaluator_model": HAIKU_MODEL,
                "prompts_and_raw_responses_preserved": True,
            },
            "sources": {"suite": str(args.suite),
                        "wrong_prompt_io": str(args.wrong_prompt_io)},
            "settings": {"variants": list(VARIANTS), "hard_limit": args.hard_limit,
                         "random_pool": args.random_pool,
                         "grade_repeats": args.grade_repeats},
            "summary": _summary(rows),
            "rows": rows,
        }
        _write_artifacts(result, args.out, args.markdown_dir)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case_id): case_id for case_id in pending}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"}
            rows[:] = [value for value in rows if value["case_no"] != case_id]
            rows.append(row)
            result = persist()
            if row.get("error"):
                print(f"[{position:02d}/{len(pending)}] {case_id} ERROR {row['error']}",
                      flush=True)
            else:
                marks = " ".join(
                    f"{variant}={'○' if row['variants'][variant]['grade']['correct'] else '✗'}"
                    for variant in VARIANTS)
                print(f"[{position:02d}/{len(pending)}] {case_id} {marks}", flush=True)
    result = persist()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
