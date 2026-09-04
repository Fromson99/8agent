#!/usr/bin/env python3
"""답변 수치·기간·비율·비교연산자·양태가 질문/동결 원문에 존재하는지 감사한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: F401,E402  # store env 설정
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


_VALUE = re.compile(
    r"(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(?P<unit>%|퍼센트|조원|억원|만원|원|개월|시간|년|일|명|인|회|주|배)"
    r"\s*(?P<comparator>이상|이하|초과|미만)?"
)
_FRACTION = re.compile(r"100\s*분의\s*(?P<number>\d+(?:\.\d+)?)"
                       r"\s*(?P<comparator>이상|이하|초과|미만)?")
_OPERATORS = {
    "EACH": re.compile(r"각각"),
    "AGGREGATE": re.compile(r"합산|합계"),
    "ANY_ONE": re.compile(r"어느\s+하나"),
    "ALL": re.compile(r"모두|전부"),
    "LESSER": re.compile(r"중\s+(?:적은|작은)"),
    "GREATER": re.compile(r"중\s+(?:큰|많은)"),
}
_MODALITIES = {
    "MUST_NOT": re.compile(r"할\s*수\s*없|하여서는\s*아니|금지|"
                           r"과세하지\s*아니|적용하지\s*아니"),
    "MAY": re.compile(r"할\s*수\s*있"),
    "MUST": re.compile(r"하여야|해야\s*한다|의무"),
    "DEEMED": re.compile(r"(?:으로|로)\s*본다|간주"),
}


def _number(value: str) -> str:
    raw = value.replace(",", "")
    return raw.rstrip("0").rstrip(".") if "." in raw else raw


def extract_values(text: str) -> list[dict]:
    out = []
    for match in _VALUE.finditer(str(text or "")):
        unit = match.group("unit")
        if unit == "퍼센트":
            unit = "%"
        out.append({
            "surface": match.group(0).strip(),
            "canonical": f"{_number(match.group('number'))}{unit}:"
                         f"{match.group('comparator') or 'EQ'}",
        })
    for match in _FRACTION.finditer(str(text or "")):
        out.append({
            "surface": match.group(0).strip(),
            "canonical": f"{_number(match.group('number'))}%:"
                         f"{match.group('comparator') or 'EQ'}",
        })
    seen = set()
    return [row for row in out if not (row["canonical"] in seen or seen.add(row["canonical"]))]


def extract_labels(text: str, patterns: dict[str, re.Pattern]) -> list[str]:
    return [name for name, pattern in patterns.items() if pattern.search(str(text or ""))]


def audit_answer(question: str, answer: str, evidence_text: str) -> dict:
    answer_values = extract_values(answer)
    evidence_values = {row["canonical"] for row in extract_values(evidence_text)}
    question_values = {row["canonical"] for row in extract_values(question)}
    unsupported_values = [row for row in answer_values
                          if row["canonical"] not in evidence_values
                          and row["canonical"] not in question_values]
    answer_operators = extract_labels(answer, _OPERATORS)
    allowed_operators = set(extract_labels(evidence_text, _OPERATORS)) \
        | set(extract_labels(question, _OPERATORS))
    unsupported_operators = [value for value in answer_operators
                             if value not in allowed_operators]
    answer_modalities = extract_labels(answer, _MODALITIES)
    allowed_modalities = set(extract_labels(evidence_text, _MODALITIES)) \
        | set(extract_labels(question, _MODALITIES))
    unsupported_modalities = [value for value in answer_modalities
                              if value not in allowed_modalities]
    return {
        "answer_values": answer_values,
        "unsupported_values": unsupported_values,
        "answer_operators": answer_operators,
        "unsupported_operators": unsupported_operators,
        "answer_modalities": answer_modalities,
        "unsupported_modalities": unsupported_modalities,
        "flagged": bool(unsupported_values or unsupported_operators
                        or unsupported_modalities),
    }


def summarize(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    flagged = [row for row in good if row.get("flagged")]
    wrong = [row for row in good if not row.get("semantic_correct")]
    correct = [row for row in good if row.get("semantic_correct")]
    wrong_flagged = sum(row.get("flagged", False) for row in wrong)
    correct_flagged = sum(row.get("flagged", False) for row in correct)
    return {
        "cases": len(good), "semantic_correct": len(correct),
        "semantic_wrong": len(wrong), "flagged": len(flagged),
        "wrong_flagged": wrong_flagged, "correct_flagged": correct_flagged,
        "flag_precision_for_semantic_error": round(wrong_flagged / len(flagged), 4)
        if flagged else 0,
        "semantic_error_recall": round(wrong_flagged / len(wrong), 4) if wrong else 0,
        "correct_answer_false_flag_rate": round(correct_flagged / len(correct), 4)
        if correct else 0,
        "unsupported_value_count": sum(len(row.get("unsupported_values") or [])
                                       for row in good),
        "unsupported_operator_counts": dict(Counter(
            value for row in good for value in row.get("unsupported_operators") or [])),
        "unsupported_modality_counts": dict(Counter(
            value for row in good for value in row.get("unsupported_modalities") or [])),
        "errors": [row.get("error") for row in rows if row.get("error")],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    args = parser.parse_args()

    answers = json.loads(args.answers.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    selected_by_case = {str(row["case_no"]):
        (((row.get("variants") or {}).get(args.variant) or {}).get("selected") or [])
        for row in retrieval.get("rows") or []}
    index = index_mod.current()
    rows = []
    for source in answers.get("rows") or []:
        case_id = str(source.get("case_no") or "")
        try:
            value = ((source.get("variants") or {}).get(args.variant) or {})
            evidence = reconstruct_evidence(index, selected_by_case[case_id])
            evidence_text = "\n".join(str(row.get("original_text") or "") for row in evidence)
            audit = audit_answer(
                str(source.get("question") or ""), str(value.get("answer") or ""),
                evidence_text)
            rows.append({"case_no": case_id,
                         "semantic_correct": bool(value.get("semantic_correct")), **audit})
        except Exception as exc:
            rows.append({"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"})
    result = {
        "experiment": "deterministic-critical-value-audit-v1",
        "contract": {
            "read_only": True, "gold_used_for_flagging": False,
            "semantic_grade_used_only_for_posthoc_scoring": True,
            "question_values_count_as_supported": True,
            "auto_block": False, "main_wiring_changed": False,
            "canonical_changed": False,
        },
        "answers": str(args.answers), "retrieval": str(args.retrieval_ablation),
        "variant": args.variant, "summary": summarize(rows), "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 1 if result["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
