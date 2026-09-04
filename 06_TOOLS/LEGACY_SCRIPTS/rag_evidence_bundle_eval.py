#!/usr/bin/env python3
"""동일 조문 원문에서 Evidence Bundle 구조화 효과를 격리해 측정한다.

    .venv/bin/python scripts/rag_evidence_bundle_eval.py \
      --out var/eval/e2e/cm_core_evidence_bundle_probe.json

검색 성능은 재지 않는다. 정답 결정항이 이미 회수됐다는 oracle 조건에서 원문만
나열했을 때와 쟁점·조문 역할·적용 범위를 붙였을 때를 비교한다. 유사 오답을 섞은
조건은 매 반복마다 순서를 바꿔 문맥 순서 민감도도 드러낸다.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 데이터 경로 환경 설정
from lawrag.core.rag import index as index_mod  # noqa: E402


SYSTEM = """너는 제공된 법령 원문만으로 질문에 답하는 법률 근거 판정기다.
규칙:
1. 결론의 핵심 문장마다 그 문장을 뒷받침하는 evidence id를 연결한다.
2. 원문에 없는 개념의 동일성, 포함관계, 관행을 추측하지 않는다.
3. 직접 근거가 없으면 없다고 밝히고 별도 법적 근거가 필요하다고 답한다.
4. 법령명, 규율 대상, 행위자, 문서 종류와 법적 효과가 다른 근거를 섞지 않는다.
5. 원문을 요약할 수는 있지만 숫자, 예외와 적용 조건을 생략하지 않는다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "decisive_evidence_ids": {
            "type": "array", "items": {"type": "string"},
        },
        "supported_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "evidence_ids": {
                        "type": "array", "items": {"type": "string"},
                    },
                },
                "required": ["claim", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "decisive_evidence_ids", "supported_claims", "unresolved"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class EvidenceSpec:
    id: str
    doc_id: str
    node: int
    role: str
    scope: dict[str, str]


@dataclass(frozen=True)
class CaseSpec:
    id: str
    question: str
    issue: dict[str, str]
    gold_id: str
    negative_id: str
    evidence: tuple[EvidenceSpec, ...]


CASES = (
    CaseSpec(
        id="cm-032",
        question=("반기보고서 제출기한 45일과 60일은 어떻게 구분되는가?\n"
                  "(업무 문맥: 반기·분기보고서의 제출기한)"),
        issue={
            "target": "반기보고서와 분기보고서",
            "actor": "사업보고서 제출대상법인",
            "legal_effect": "제출기한 45일 원칙과 60일 특례의 적용 조건",
        },
        gold_id="G32",
        negative_id="N32",
        evidence=(
            EvidenceSpec(
                id="G32", doc_id="9a51fdb8028417bf", node=1473,
                role="반기·분기보고서 제출기한 규정",
                scope={"actor": "사업보고서 제출대상법인",
                       "object": "반기보고서·분기보고서",
                       "effect": "제출기한과 특례"},
            ),
            EvidenceSpec(
                id="N32", doc_id="c6d784d914932b53", node=366,
                role="신용평가회사 업무보고서 제출기한 규정",
                scope={"actor": "신용평가회사", "object": "업무보고서",
                       "effect": "매분기 종료 후 제출기한"},
            ),
        ),
    ),
    CaseSpec(
        id="cm-036",
        question=("내부회계관리자는 등기임원이어야 하는가?\n"
                  "(업무 문맥: 내부회계관리제도)"),
        issue={
            "target": "내부회계관리자",
            "actor": "회사의 대표자가 지정하는 담당자",
            "legal_effect": "등기임원 자격이 법적 요건인지 여부",
        },
        gold_id="G36",
        negative_id="N36",
        evidence=(
            EvidenceSpec(
                id="G36", doc_id="8e6b9251fdfba8f4", node=60,
                role="내부회계관리자의 지정 요건",
                scope={"actor": "회사의 대표자", "object": "내부회계관리자",
                       "effect": "상근이사 또는 해당 업무 집행자 지정"},
            ),
            EvidenceSpec(
                id="N36", doc_id="c66045625265ad5c", node=612,
                role="상장신청 서류의 기재사항",
                scope={"actor": "상장법인·내부회계관리자",
                       "object": "내부회계관리제도 운영보고서",
                       "effect": "보고서에 포함할 사항"},
            ),
        ),
    ),
)

VARIANTS = (
    "raw_gold",
    "structured_gold",
    "raw_mixed",
    "structured_mixed",
)


def _material(index, spec: EvidenceSpec) -> dict[str, Any]:
    view = index.docs[spec.doc_id]
    node = view.by_id[spec.node]
    return {
        "id": spec.id,
        "document": view.name,
        "path": view.path(spec.node),
        "role": spec.role,
        "scope": spec.scope,
        "original_text": view.section_text(node, cap=20_000),
    }


def build_prompt(case: CaseSpec, variant: str, materials: list[dict[str, Any]],
                 *, seed: int) -> tuple[str, list[str]]:
    """프롬프트와 실제 제시 순서를 만든다. mixed만 반복별로 순서를 바꾼다."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    selected = [row for row in materials if row["id"] == case.gold_id]
    if variant.endswith("mixed"):
        selected = list(materials)
        random.Random(seed).shuffle(selected)
    order = [str(row["id"]) for row in selected]

    if variant.startswith("raw_"):
        evidence = "\n\n".join(
            f"[{row['id']}]\n법령: {row['document']}\n위치: {row['path']}\n"
            f"원문:\n{row['original_text']}"
            for row in selected
        )
        payload = f"[질문]\n{case.question}\n\n[근거 원문]\n{evidence}"
    else:
        bundle = {
            "question": case.question,
            "issue_frame": case.issue,
            "evidence": selected,
        }
        payload = "[Evidence Bundle]\n" + json.dumps(
            bundle, ensure_ascii=False, indent=2)
    return payload, order


def score(case: CaseSpec, response: dict[str, Any] | None) -> dict[str, Any]:
    """정답 문구를 프롬프트에 노출하지 않고 결과 파일에서 결정론적으로 채점한다."""
    if not response:
        return {"passed": False, "checks": {"response": False}}
    answer = re.sub(r"\s+", "", str(response.get("answer") or ""))
    decisive = set(map(str, response.get("decisive_evidence_ids") or []))
    checks: dict[str, bool] = {
        "gold_decisive": case.gold_id in decisive,
        "negative_not_decisive": case.negative_id not in decisive,
    }
    if case.id == "cm-032":
        checks.update({
            "states_45_days": "45일" in answer,
            "states_60_days": "60일" in answer,
            "states_connected_basis": "연결재무제표" in answer,
            "states_first_two_years": bool(
                re.search(r"최초(?:의)?사업연도", answer)
                and "다음사업연도" in answer
            ),
        })
    elif case.id == "cm-036":
        no_direct_basis = any(re.search(pattern, answer) for pattern in (
            r"등기(?:이사|임원).{0,30}(?:직접|명시).{0,30}(?:없|않|단정할수없)",
            r"(?:직접|명시).{0,30}등기(?:이사|임원).{0,30}(?:없|않)",
            r"등기(?:이사|임원).{0,30}(?:동일|의미).{0,30}(?:근거가없|단정할수없)",
            r"등기(?:이사|임원).{0,30}(?:여부).{0,30}(?:별도|해석)",
        ))
        invalid_equivalence = any(re.search(pattern, answer) for pattern in (
            r"상근(?:이사|임원)(?:은|는|이|가)?등기(?:이사|임원)(?:을|를)?(?:의미|말함|말한다)",
            r"상근(?:이사|임원).{0,12}등기(?:이사|임원).{0,12}(?:동일|해당한다)",
        ))
        categorical_no = any(re.search(pattern, answer) for pattern in (
            r"^(?:아니다|아닙니다)",
            r"등기(?:이사|임원)(?:이어야|일)하지않",
            r"등기(?:이사|임원)일필요가없",
            r"등기(?:이사|임원)(?:이어야)?하는것은아니",
            r"등기(?:이사|임원)자격을(?:법적)?요건으로명시하지않",
        ))
        separate_basis = any(word in answer for word in (
            "별도의법적근거", "별도법적근거", "별도검토", "상법상",
            "해석에의", "단정할수없", "확인할수없",
        ))
        checks.update({
            "states_standing_director": "상근이사" in answer,
            "rejects_direct_equivalence": no_direct_basis,
            "no_invalid_equivalence": not invalid_equivalence,
            "avoids_categorical_no": not categorical_no,
            "requires_separate_basis": separate_basis,
        })
    return {"passed": all(checks.values()), "checks": checks}


def _usage(exchange) -> dict[str, Any]:
    return {
        "input_tokens": int((exchange.usage or {}).get("input_tokens", 0)),
        "output_tokens": int((exchange.usage or {}).get("output_tokens", 0)),
        "duration_ms": int(exchange.dur_ms),
        "error": str(exchange.error or ""),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def stats(selected: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "runs": len(selected),
            "passed": sum(bool(row["score"]["passed"]) for row in selected),
            "pass_rate": round(
                sum(bool(row["score"]["passed"]) for row in selected) / len(selected), 4
            ) if selected else 0,
            "input_tokens": sum(row["usage"]["input_tokens"] for row in selected),
            "output_tokens": sum(row["usage"]["output_tokens"] for row in selected),
            "duration_ms": sum(row["usage"]["duration_ms"] for row in selected),
            "errors": sum(bool(row["usage"]["error"]) for row in selected),
        }

    by_variant = {}
    for variant in VARIANTS:
        selected = [row for row in rows if row["variant"] == variant]
        by_variant[variant] = stats(selected)
    by_case = {
        case.id: {
            variant: stats([
                row for row in rows
                if row["case_no"] == case.id and row["variant"] == variant
            ])
            for variant in VARIANTS
        }
        for case in CASES
    }
    return {"runs": len(rows), "by_variant": by_variant, "by_case": by_case}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument(
        "--rescore-existing", action="store_true",
        help="저장된 응답을 현재 결정론적 채점기로만 다시 채점한다")
    args = parser.parse_args()

    if args.rescore_existing:
        result = json.loads(args.out.read_text(encoding="utf-8"))
        cases = {case.id: case for case in CASES}
        for row in result.get("rows") or []:
            row["score"] = score(cases[row["case_no"]], row.get("response"))
        result["scorer_version"] = 2
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
    rows: list[dict[str, Any]] = []
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for case in CASES:
        materials = [_material(index, spec) for spec in case.evidence]
        for variant in VARIANTS:
            for repeat in range(1, args.repeats + 1):
                run_seed = args.seed + repeat + sum(map(ord, case.id + variant))
                prompt, order = build_prompt(
                    case, variant, materials, seed=run_seed)
                started = time.perf_counter()
                response = llm.structured(
                    "rag.evidence_bundle_eval", SYSTEM, prompt, SCHEMA,
                    max_tokens=1800, effort="low")
                exchange = llm.log[-1]
                row = {
                    "case_no": case.id,
                    "variant": variant,
                    "repeat": repeat,
                    "evidence_order": order,
                    "response": response,
                    "score": score(case, response),
                    "usage": _usage(exchange),
                    "wall_ms": round((time.perf_counter() - started) * 1000),
                }
                rows.append(row)
                result = {
                    "experiment": "evidence-bundle-oracle-v1",
                    "scorer_version": 2,
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
                      f"order={','.join(order)} in={row['usage']['input_tokens']} "
                      f"out={row['usage']['output_tokens']} "
                      f"wall={row['wall_ms']}ms", flush=True)

    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
