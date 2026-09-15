#!/usr/bin/env python3
"""CM 원본 DOCX에 동결 Golden v3의 최소충분 조문 좌표를 주석한다.

원본과 골든을 수정하지 않고 별도 DOCX와 결정론적 검증 JSON을 만든다.
좌표의 채점 단위는 항·호가 아닌 canonical article-root다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
DEFAULT_SOURCE = ROOT / "[CM본부] 주요 법규정 질의 등_260819.docx"
DEFAULT_SUITE = ROOT / "01_DATA/review/cm_core_e2e_v3.json"
DEFAULT_OUTPUT = ROOT / "09_ARTIFACTS/REPORTS/DOCUMENTS/[CM본부] 주요 법규정 질의 등_260819_골든좌표_검증본.docx"
DEFAULT_REPORT = (
    ROOT
    / "docs/adr/ADR-0140-cm-source-golden-coordinate-annotation/artifacts/run-001.json"
)

ROLE_LABELS = {
    "MAIN": "주된 판단근거",
    "INCORPORATED_RULE": "준용되는 실질규정",
    "CONDITION_EXCEPTION": "조건·예외",
    "DEFINITION": "정의",
    "DELEGATED_DETAIL": "위임 세부규정",
    "DELEGATION_BRIDGE": "위임 연결조문",
    "INCORPORATION_BRIDGE": "준용 연결조문",
    "TEMPORAL_TRANSITION": "경과·시점규정",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _insert_after(paragraph: Paragraph, text: str) -> Paragraph:
    element = OxmlElement("w:p")
    paragraph._p.addnext(element)
    inserted = Paragraph(element, paragraph._parent)
    inserted.style = paragraph.style
    inserted.add_run(text)
    return inserted


def _shade(paragraph: Paragraph, fill: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _source_pairs(document: Document) -> tuple[list[Paragraph], list[Paragraph]]:
    questions: list[Paragraph] = []
    answers: list[Paragraph] = []
    for paragraph in document.paragraphs:
        text = _normalized(paragraph.text)
        if re.search(r"\((?:추가)?질문\)", text):
            questions.append(paragraph)
        if re.search(r"\((?:추가)?답변\)", text):
            answers.append(paragraph)
    return questions, answers


def _question_text(text: str) -> str:
    text = re.sub(r"^\d+(?:\.\d+)?\.\s*", "", _normalized(text))
    return re.sub(r"^\((?:추가)?질문\)\s*", "", text)


def _answer_text(text: str) -> str:
    return re.sub(r"^\((?:추가)?답변\)\s*", "", _normalized(text))


def _validate_corpus_coordinate(article: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    doc_id = str(article.get("doc_id") or "")
    node_id = str(article.get("node") or "")
    result_path = ROOT / "01_DATA/structure" / doc_id / "result.json"
    meta_path = result_path.with_name("meta.json")
    if not result_path.is_file() or not meta_path.is_file():
        return [f"missing_document:{doc_id}"]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if str(meta.get("name") or "") != str(article.get("law") or ""):
        errors.append(f"law:{doc_id}:{meta.get('name')}:{article.get('law')}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    nodes = [row for row in result.get("nodes") or [] if str(row.get("id")) == node_id]
    if len(nodes) != 1:
        errors.append(f"node:{doc_id}:{node_id}:{len(nodes)}")
    elif str(nodes[0].get("surface") or "") != str(article.get("article") or ""):
        errors.append(
            f"surface:{doc_id}:{node_id}:{nodes[0].get('surface')}:{article.get('article')}"
        )
    return errors


def annotate(source: Path, suite_path: Path, output: Path, report_path: Path) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = list(suite.get("cases") or [])
    source_sha = _sha256(source)
    expected_source_sha = str((suite.get("source") or {}).get("sha256") or "")
    errors: list[str] = []
    if source_sha != expected_source_sha:
        errors.append(f"source_sha256:{expected_source_sha}:{source_sha}")
    if len(cases) != 51:
        errors.append(f"case_count:{len(cases)}")

    document = Document(source)
    questions, answers = _source_pairs(document)
    if len(questions) != 52 or len(answers) != 51:
        errors.append(f"source_counts:questions={len(questions)}:answers={len(answers)}")

    coordinate_count = 0
    role_counts: Counter[str] = Counter()
    case_receipts: list[dict[str, Any]] = []
    if not errors:
        for index, (case, answer) in enumerate(zip(cases, answers, strict=True)):
            question = questions[index + 1]  # 첫 문단은 답변 없는 컨테이너 질문이다.
            if _question_text(question.text) != str(case.get("source_question") or ""):
                errors.append(f"{case.get('id')}:source_question")
            if _answer_text(answer.text) != str(case.get("reference_answer") or ""):
                errors.append(f"{case.get('id')}:reference_answer")

            articles = list(case.get("evidence_articles") or [])
            if not articles:
                errors.append(f"{case.get('id')}:no_evidence_articles")
                continue
            header = _insert_after(
                answer,
                f"[골든 좌표 | {case['id']} | article-root {len(articles)}개]",
            )
            _shade(header, "D9EAF7")
            cursor = header
            coordinates: list[dict[str, str]] = []
            for article in articles:
                role = str(article.get("evidence_role_v3") or "")
                role_counts[role] += 1
                coordinate_count += 1
                corpus_errors = _validate_corpus_coordinate(article)
                errors.extend(f"{case.get('id')}:{value}" for value in corpus_errors)
                text = (
                    f"• {ROLE_LABELS.get(role, role)}({role}) | "
                    f"{article.get('law')} {article.get('article')} | "
                    f"{article.get('coordinate_key')} | doc_id={article.get('doc_id')} | "
                    f"node={article.get('node')} | 기준일={article.get('authority_as_of')} | "
                    f"corpus={article.get('corpus_status')}"
                )
                cursor = _insert_after(cursor, text)
                _shade(cursor, "EDF5FB")
                coordinates.append(
                    {
                        "law": str(article.get("law") or ""),
                        "article": str(article.get("article") or ""),
                        "role": role,
                        "coordinate_key": str(article.get("coordinate_key") or ""),
                        "doc_id": str(article.get("doc_id") or ""),
                        "node": str(article.get("node") or ""),
                    }
                )
            case_receipts.append({"case_id": case["id"], "coordinates": coordinates})

    if coordinate_count != 98:
        errors.append(f"coordinate_count:{coordinate_count}")
    if errors:
        raise ValueError("; ".join(errors))

    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    reopened = Document(output)
    annotated_texts = [paragraph.text for paragraph in reopened.paragraphs]
    header_count = sum(text.startswith("[골든 좌표 | cm-") for text in annotated_texts)
    embedded_coordinate_count = sum(text.startswith("• ") for text in annotated_texts)
    original_texts = [paragraph.text for paragraph in Document(source).paragraphs]
    clean_annotated = [
        text
        for text in annotated_texts
        if not text.startswith("[골든 좌표 | cm-") and not text.startswith("• ")
    ]
    roundtrip_original_preserved = clean_annotated == original_texts
    if header_count != 51 or embedded_coordinate_count != 98 or not roundtrip_original_preserved:
        raise ValueError(
            "roundtrip_validation:"
            f"headers={header_count}:coordinates={embedded_coordinate_count}:"
            f"original_preserved={roundtrip_original_preserved}"
        )

    report = {
        "schema_version": "cm-golden-coordinate-docx-audit-v1",
        "status": "complete",
        "source": {"path": str(source), "sha256": source_sha, "unchanged": True},
        "suite": {
            "path": str(suite_path),
            "sha256": _sha256(suite_path),
            "version": str(suite.get("version") or ""),
            "authority_as_of": "20260827",
        },
        "output": {"path": str(output), "sha256": _sha256(output), "bytes": output.stat().st_size},
        "counts": {
            "source_questions": len(questions),
            "source_answers": len(answers),
            "scorable_cases": len(cases),
            "excluded_container_questions": 1,
            "annotated_cases": header_count,
            "golden_coordinates": coordinate_count,
            "embedded_coordinates": embedded_coordinate_count,
        },
        "role_counts": dict(sorted(role_counts.items())),
        "validation": {
            "source_hash_matches_frozen": source_sha == expected_source_sha,
            "question_answer_alignment": "51/51",
            "coordinate_embedding": "98/98",
            "corpus_coordinate_resolution": "98/98",
            "docx_roundtrip": True,
            "original_paragraphs_preserved": roundtrip_original_preserved,
            "llm_calls": 0,
            "retrieval_calls": 0,
        },
        "cases": case_receipts,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = annotate(args.source, args.suite, args.output, args.report)
    counts = report["counts"]
    print(
        f"PASS: {counts['annotated_cases']}/51 사례·"
        f"{counts['embedded_coordinates']}/98 좌표 주석, "
        f"원본 문단 보존, DOCX 재열기 통과"
    )
    print(args.output)
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
