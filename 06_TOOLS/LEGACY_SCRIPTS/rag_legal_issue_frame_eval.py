#!/usr/bin/env python3
"""IssueFrame → 해석 후보 → 3값 근거 판정의 oracle probe를 실행한다."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import review_golden as review  # noqa: E402
from scripts.rag_evidence_bundle_eval import CASES, _material  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legalissue  # noqa: E402


VARIANTS = ("framed_gold", "framed_mixed")


def _usage(exchanges) -> dict[str, Any]:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((row.usage or {}).get("input_tokens", 0))
                            for row in exchanges),
        "output_tokens": sum(int((row.usage or {}).get("output_tokens", 0))
                             for row in exchanges),
        "duration_ms": sum(int(row.dur_ms) for row in exchanges),
        "errors": sum(bool(row.error) for row in exchanges),
    }


def score(case, frame: dict[str, Any] | None,
          judgment: dict[str, Any] | None, answer: str) -> dict[str, Any]:
    if not frame or not judgment:
        return {"passed": False, "checks": {"complete": False}}
    proposition = re.sub(r"\s+", "", str(frame.get("proposition") or ""))
    answer_packed = re.sub(r"\s+", "", answer)
    controlling = set(map(str, judgment.get("controlling_evidence_ids") or []))
    material = {
        str(row.get("evidence_id") or "")
        for row in judgment.get("rule_findings") or []
    }
    interpreters = set(map(str, frame.get("candidate_interpreters") or []))
    checks = {
        # not_determined는 결론을 확정할 controlling 근거가 없는 것이 정상이다.
        # 대신 질문 판단에 실제 사용한 material finding에 gold가 있어야 한다.
        "gold_material": case.gold_id in material,
        "negative_not_controlling": case.negative_id not in controlling,
    }
    if case.id == "cm-032":
        checks.update({
            "frame_preserves_deadlines": "45" in proposition and "60" in proposition,
            "selects_rule_interpreter": bool(
                interpreters & {"literal", "subsumption", "exception",
                                "evidence_sufficiency"}),
            "verdict_entailed": judgment.get("verdict") == "entailed",
            "states_45_and_60": "45일" in answer_packed and "60일" in answer_packed,
            "states_connected_basis": "연결재무제표" in answer_packed,
            "states_first_two_years": bool(
                "최초" in answer_packed
                and ("다음사업연도" in answer_packed or "차년도" in answer_packed
                     or "최초2개사업연도" in answer_packed)),
        })
    else:
        missing = re.sub(
            r"\s+", "", " ".join(map(str, judgment.get("missing_links") or [])))
        categorical_no = any(re.search(pattern, answer_packed) for pattern in (
            r"^(?:아니다|아닙니다)",
            r"등기(?:이사|임원)(?:이어야|일)하지않",
            r"등기(?:이사|임원)일필요가없",
            r"등기(?:이사|임원)(?:이어야)?하는것은아니",
        ))
        guard_missing = " ".join(map(
            str, judgment.get("guard_missing_decision_terms") or []))
        checks.update({
            "frame_preserves_proposition": (
                "내부회계관리자" in proposition and "등기임원" in proposition),
            "selects_relation_interpreter": bool(
                interpreters & {"definition_scope", "subsumption", "cross_statute"}),
            "verdict_not_determined": judgment.get("verdict") == "not_determined",
            "identifies_missing_bridge": (
                "등기" in missing
                and ("상근" in missing or "상법" in missing
                     or "내부회계관리자" in missing)
                or "등기임원" in guard_missing),
            "answer_is_conservative": (
                "확정할수없" in answer_packed and not categorical_no),
            "answer_shows_standing_director_text": "상근이사" in answer_packed,
        })
    # exact quote가 탈락해 material trace가 비어도 결론 극성 자체는 안전할 수 있다.
    # 운영 채택에는 둘 다 필요하므로 strict(passed)와 safety를 함께 보존한다.
    safety_checks = {key: value for key, value in checks.items()
                     if key != "gold_material"}
    return {
        "passed": all(checks.values()),
        "safety_passed": all(safety_checks.values()),
        "checks": checks,
    }


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": len(rows),
        "passed": sum(bool(row["score"]["passed"]) for row in rows),
        "safety_passed": sum(
            bool(row["score"].get("safety_passed")) for row in rows),
        "pass_rate": round(
            sum(bool(row["score"]["passed"]) for row in rows) / len(rows), 4
        ) if rows else 0,
        "calls": sum(row["usage"]["calls"] for row in rows),
        "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
        "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
        "duration_ms": sum(row["usage"]["duration_ms"] for row in rows),
        "errors": sum(row["usage"]["errors"] for row in rows),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": len(rows),
        "by_variant": {
            variant: _stats([row for row in rows if row["variant"] == variant])
            for variant in VARIANTS
        },
        "by_case": {
            case.id: {
                variant: _stats([
                    row for row in rows
                    if row["case_no"] == case.id and row["variant"] == variant
                ])
                for variant in VARIANTS
            }
            for case in CASES
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument(
        "--rescore-existing", action="store_true",
        help="저장된 frame·판정·답변을 현재 채점기로만 다시 채점한다")
    args = parser.parse_args()

    if args.rescore_existing:
        result = json.loads(args.out.read_text(encoding="utf-8"))
        cases = {case.id: case for case in CASES}
        for row in result.get("rows") or []:
            if "score_v1" not in row:
                row["score_v1"] = row.get("score")
            if int(result.get("scorer_version") or 1) == 2 and "score_v2" not in row:
                row["score_v2"] = row.get("score")
            row["score"] = score(
                cases[row["case_no"]], row.get("frame"), row.get("judgment"),
                str(row.get("answer") or ""))
        result["scorer_version"] = 4
        result["summary"] = _summary(result.get("rows") or [])
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 0

    llm = review._llm()
    if llm is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    rows = []
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for case in CASES:
        materials = [_material(index, spec) for spec in case.evidence]
        for variant in VARIANTS:
            for repeat in range(1, args.repeats + 1):
                evidence = [row for row in materials if row["id"] == case.gold_id]
                if variant == "framed_mixed":
                    evidence = list(materials)
                    seed = args.seed + repeat + sum(map(ord, case.id + variant))
                    random.Random(seed).shuffle(evidence)
                start_log = len(llm.log)
                started = time.perf_counter()
                frame = legalissue.structure_question(llm, case.question)
                judgment_raw = legalissue.judge_evidence(
                    llm, frame or {}, evidence) if frame else None
                judgment = legalissue.verify_judgment(judgment_raw, evidence, frame)
                answer = legalissue.render_answer(frame or {}, judgment)
                usage = _usage(llm.log[start_log:])
                row = {
                    "case_no": case.id,
                    "variant": variant,
                    "repeat": repeat,
                    "evidence_order": [str(item["id"]) for item in evidence],
                    "frame": frame,
                    "active_interpreters": legalissue.interpreter_instructions(frame or {}),
                    "judgment_raw": judgment_raw,
                    "judgment": judgment,
                    "answer": answer,
                    "score": score(case, frame, judgment, answer),
                    "usage": usage,
                    "wall_ms": round((time.perf_counter() - started) * 1000),
                }
                rows.append(row)
                result = {
                    "experiment": "legal-issue-frame-typed-decision-guard-oracle-v5",
                    "scorer_version": 4,
                    "model": llm.model,
                    "repeats": args.repeats,
                    "seed": args.seed,
                    "conditions": list(VARIANTS),
                    "summary": _summary(rows),
                    "rows": rows,
                }
                args.out.write_text(
                    json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
                mark = "PASS" if row["score"]["passed"] else "FAIL"
                print(f"{case.id} {variant} #{repeat} {mark} "
                      f"verdict={(judgment or {}).get('verdict')} "
                      f"order={','.join(row['evidence_order'])} "
                      f"calls={usage['calls']} in={usage['input_tokens']} "
                      f"out={usage['output_tokens']} wall={row['wall_ms']}ms",
                      flush=True)

    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
