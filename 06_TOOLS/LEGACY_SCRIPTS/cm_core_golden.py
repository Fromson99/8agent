#!/usr/bin/env python3
"""CM본부 현업 질의응답 핵심 골든의 원문·정답·근거 좌표를 검증한다.

    .venv/bin/python scripts/cm_core_golden.py
    .venv/bin/python scripts/cm_core_golden.py --json

이 스크립트는 골든을 다시 생성하지 않는다. 동결 JSON이 첨부 DOCX의 실제 질문과
답변을 그대로 보존하는지, 현재 코퍼스에 정답 조문이 있는지를 읽기 전용으로 확인한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "data" / "review" / "cm_core_e2e_v2.json"


def _source_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    questions: list[dict[str, Any]] = []
    answers: list[str] = []
    topic = ""
    topic_no = 0
    for paragraph in Document(path).paragraphs:
        text = " ".join(paragraph.text.split())
        heading = re.match(r"^(\d+)\.\s+(.+)$", text)
        if heading and "(추가질문)" not in text:
            topic_no = int(heading.group(1))
            topic = heading.group(2)
        if re.search(r"\((?:추가)?질문\)", text):
            question = re.sub(r"^\d+(?:\.\d+)?\.\s*", "", text)
            kind = "additional" if "(추가질문)" in question else "primary"
            question = re.sub(r"^\((?:추가)?질문\)\s*", "", question)
            questions.append({
                "source_question_no": len(questions) + 1,
                "topic_no": topic_no,
                "topic": topic,
                "question_kind": kind,
                "source_question": question,
            })
        if re.search(r"\((?:추가)?답변\)", text):
            answers.append(re.sub(r"^\((?:추가)?답변\)\s*", "", text))
    return questions, answers


def _corpus_articles() -> dict[tuple[str, str], list[dict[str, str]]]:
    found: dict[tuple[str, str], list[dict[str, str]]] = {}
    for meta_path in (ROOT / "data" / "structure").glob("*/meta.json"):
        result_path = meta_path.with_name("result.json")
        if not result_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        # 법령 개정 이력은 같은 법령명·조문 좌표를 가진 구조 문서를 보존한다.
        # 골든의 current_material은 현행 코퍼스 가용성을 뜻하므로 구판까지
        # 세면 정상적인 개정 이력을 ambiguous_article로 오판한다.
        if str(meta.get("status") or "").strip() == "구판":
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for node in result.get("nodes") or []:
            if node.get("family") != "kr_article":
                continue
            if node.get("coordinate_scope") not in (None, "", "body"):
                continue
            key = (str(meta.get("name") or ""), str(node.get("surface") or ""))
            found.setdefault(key, []).append({
                "doc_id": str(meta.get("doc_id") or meta_path.parent.name),
                "node": str(node.get("id")),
            })
    return found


def validate(suite_path: Path) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    source_path = ROOT / str((suite.get("source") or {}).get("path") or "")
    errors: list[str] = []
    warnings: list[str] = []
    if not source_path.is_file():
        return {"valid": False, "errors": [f"missing_source:{source_path}"],
                "warnings": [], "suite": str(suite_path)}

    expected_sha = str((suite.get("source") or {}).get("sha256") or "")
    actual_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if expected_sha != actual_sha:
        errors.append(f"source_sha256:{expected_sha}:{actual_sha}")

    questions, answers = _source_rows(source_path)
    cases = list(suite.get("cases") or [])
    excluded = list(suite.get("excluded_questions") or [])
    counts = dict(suite.get("counts") or {})
    actual_counts = {
        "source_questions": len(questions), "source_answers": len(answers),
        "scorable_cases": len(cases), "excluded_questions": len(excluded),
    }
    if any(counts.get(key) != value for key, value in actual_counts.items()):
        errors.append(f"counts:{counts}:{actual_counts}")
    if len(questions) != len(answers) + 1:
        errors.append(f"source_pairing:{len(questions)}:{len(answers)}")
    if not excluded or int(excluded[0].get("source_question_no", 0)) != 1:
        errors.append("excluded_container_question")

    ids = [str(case.get("id") or "") for case in cases]
    if len(ids) != len(set(ids)) or ids != [f"cm-{i:03d}" for i in range(1, 52)]:
        errors.append("case_ids")

    for pos, case in enumerate(cases):
        source_question = questions[pos + 1]
        reference_answer = answers[pos]
        for key in ("source_question_no", "topic_no", "topic", "question_kind",
                    "source_question"):
            if case.get(key) != source_question.get(key):
                errors.append(f"{case.get('id')}:{key}")
        if case.get("reference_answer") != reference_answer:
            errors.append(f"{case.get('id')}:reference_answer")
        standalone = (source_question["source_question"]
                      + f"\n(업무 문맥: {source_question['topic']})")
        if case.get("question") != standalone:
            errors.append(f"{case.get('id')}:single_turn_question")
        reference_sha = hashlib.sha256(
            (source_question["source_question"] + "\n" + reference_answer).encode()
        ).hexdigest()
        if case.get("reference_sha256") != reference_sha:
            errors.append(f"{case.get('id')}:reference_sha256")
        if not case.get("expected_articles"):
            errors.append(f"{case.get('id')}:expected_articles")
        if any(row.get("evidence_role") != "decisive"
               for row in case.get("expected_articles") or []):
            errors.append(f"{case.get('id')}:decisive_role")
        if any(row.get("evidence_role") != "required_companion"
               for row in case.get("required_companions") or []):
            errors.append(f"{case.get('id')}:companion_role")
        for axis in suite.get("axis_order") or []:
            if axis not in (case.get("axes") or {}):
                errors.append(f"{case.get('id')}:axis:{axis}")

    corpus = _corpus_articles()
    current_material: Counter[str] = Counter()
    drift = []
    for case in cases:
        statuses = []
        for expected in case.get("expected_articles") or []:
            key = (str(expected.get("law") or ""), str(expected.get("article") or ""))
            rows = corpus.get(key) or []
            status = "present" if len(rows) == 1 else (
                "missing_article" if not rows else "ambiguous_article")
            statuses.append(status)
            if status != str(expected.get("corpus_status") or ""):
                drift.append({"id": case["id"], "law": key[0], "article": key[1],
                              "frozen": expected.get("corpus_status"), "current": status})
        material = ("complete" if statuses and set(statuses) == {"present"}
                    else "missing" if "present" not in statuses else "partial")
        current_material[material] += 1
    if drift:
        warnings.append(f"corpus_resolution_drift:{len(drift)}")

    return {
        "valid": not errors, "suite": str(suite_path), "source": str(source_path),
        "source_sha256": actual_sha, "counts": actual_counts,
        "axes": list(suite.get("axis_order") or []),
        "business_domains": dict(Counter(
            str((case.get("axes") or {}).get("business_domain") or "")
            for case in cases)),
        "current_material": dict(current_material), "corpus_drift": drift,
        "turn_contract": {
            "mode": str((suite.get("turn_contract") or {}).get("mode") or ""),
            "standalone_cases": sum(bool(case.get("question")) for case in cases),
            "additional_cases": sum(case.get("question_kind") == "additional"
                                    for case in cases),
        },
        "errors": errors, "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate(args.suite)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mark = "PASS" if report["valid"] else "FAIL"
        counts = report.get("counts") or {}
        print(f"CM 현업 핵심 골든 {mark} · 질문 {counts.get('source_questions', 0)}"
              f" · 기준답변 {counts.get('source_answers', 0)}"
              f" · 평가 {counts.get('scorable_cases', 0)}")
        print("  현재 재료 " + " · ".join(
            f"{key} {value}" for key, value in
            (report.get("current_material") or {}).items()))
        if report.get("corpus_drift"):
            print(f"  코퍼스 좌표 변화 {len(report['corpus_drift'])}건")
        for error in report.get("errors") or []:
            print(f"  ✗ {error}")
        for warning in report.get("warnings") or []:
            print(f"  ! {warning}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
