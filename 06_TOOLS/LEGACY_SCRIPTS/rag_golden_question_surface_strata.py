#!/usr/bin/env python3
"""Classify frozen golden questions by explicit surface signal.

This is an offline, deterministic audit.  It never calls retrieval or an LLM and
does not read legal article bodies.  The source-question and current runtime
question are classified separately so injected CM business context remains
observable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
ADR_ID = "ADR-0083"
EXPERIMENT_ID = "ADR-0083-experiment-v1"
RUN_ID = "run-001"
MANIFEST = (
    ROOT / "docs/adr/ADR-0083-golden-question-surface-strata/실험/manifest.json"
)
OUTPUT = (
    ROOT / "docs/adr/ADR-0083-golden-question-surface-strata/artifacts/run-001.json"
)
CM_PATH = ROOT / "data/review/cm_core_e2e_v1.json"
FSC_PATH = ROOT / "data/review/fsc_hard_retrieval_v1.json"
CM_SHA256 = "d3e4f658d8c9abb06244557b669d37d63b0e6fcc879059506e3b462619bcc18d"
FSC_SHA256 = "4373659368de7a81b7e9ee48233c8b317d863db4e5c4827f4346d09281b3d7f8"
DATASET_SHA256 = "05936e4bee0ae42a90c3d20a83ff40af2bb5b47895f1702d2716b18dd82f203e"

ARTICLE_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])제\s*\d+(?:\s*-\s*\d+)?\s*"
    r"(?:조(?:의\s*\d+)?|항|호)"
)
AUTHORITY_SURFACES = (
    "코스닥시장 상장규정",
    "유가증권시장 상장규정",
    "상증세법 시행령",
    "전자금융감독규정",
    "금융회사의 지배구조에 관한 법률",
    "개인금융채권의관리 및 개인금융채무자의 보호에 관한 법률",
)
LABELS = ("authority-explicit", "keyword-explicit", "latent-only")


# Closed adjudication ledger.  Every value must be an exact continuous substring
# of the source view.  Empty tuples intentionally declare latent-only unless an
# authority expression is present.
SOURCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cm-001": ("벤처금융", "전문투자자"),
    "cm-002": (),
    "cm-003": ("재무적투자자", "제3자배정"),
    "cm-004": ("괴리율",),
    "cm-005": ("유가증권시장", "벤처금융", "전문투자자", "의무보유"),
    "cm-006": ("유가증권시장", "전문투자자"),
    "cm-007": ("상장주선인", "의무인수"),
    "cm-008": (),
    "cm-009": ("의무인수",),
    "cm-010": ("의무인수분", "공동주관회사"),
    "cm-011": ("사내규정 정비", "상장심사"),
    "cm-012": (),
    "cm-013": ("벤처기업", "주식매수선택권"),
    "cm-014": ("기준시가",),
    "cm-015": (),
    "cm-016": ("벤처기업 주식매수선택권",),
    "cm-017": ("행사가격", "부여일 기준 시가"),
    "cm-018": (),
    "cm-019": ("평가심의위원회",),
    "cm-020": ("공모가격",),
    "cm-021": (),
    "cm-022": ("비상장주식", "보충적 평가"),
    "cm-023": ("상장차익 증여의제",),
    "cm-024": (),
    "cm-025": ("과세된 저가분",),
    "cm-026": ("유상증자", "신주"),
    "cm-027": ("벤처기업 주식매수선택권 행사이익",),
    "cm-028": ("적격주식매수선택권",),
    "cm-029": ("주식매수선택권", "취득가액"),
    "cm-030": ("증권신고서", "검토보고서"),
    "cm-031": ("거래소 규정", "재무서류"),
    "cm-032": ("반기보고서 제출기한",),
    "cm-033": ("연결기준", "별도기준"),
    "cm-034": ("사업보고서 제출대상법인",),
    "cm-035": ("내부회계관리제도",),
    "cm-036": ("내부회계관리자", "등기임원"),
    "cm-037": ("감사인의 검토",),
    "cm-038": (),
    "cm-039": ("주주총회", "이사회"),
    "cm-040": ("정관 변경",),
    "cm-041": ("상장회사",),
    "cm-042": ("사외이사",),
    "cm-043": ("감사 보수", "이사회"),
    "cm-044": ("감사위원 분리선출",),
    "cm-045": ("자기주식 소각의무",),
    "cm-046": ("자기주식", "처분"),
    "cm-047": ("우리사주조합원 배정",),
    "cm-048": (),
    "cm-049": ("공동주관 의무", "주관회사"),
    "cm-050": (),
    "cm-051": (),
    "fsc-hard-001": ("전산자료", "원격 안전지역", "재해복구센터"),
    "fsc-hard-002": ("상근임원", "SPAC", "겸직제한"),
    "fsc-hard-003": ("준법감시인", "채무조정 전담인력"),
    "fsc-hard-004": ("국채통합계좌", "국채 투자매매업자"),
    "fsc-hard-005": ("준법감시인", "위험관리책임자", "겸직"),
    "fsc-hard-006": ("투자계약", "대주주", "주요주주"),
    "fsc-hard-007": ("투자매매업자", "신용공여", "예탁증권 담보융자"),
    "fsc-hard-008": ("사업보고서 제출", "모집 또는 매출", "소유자 수"),
    "fsc-hard-009": ("투자자문계약", "업무위수탁 계약"),
    "fsc-hard-010": ("투자일임·자문업자", "신용정보", "업무수탁자"),
}

# Runtime-only evidence introduced by the CM ``(업무 문맥: ...)`` suffix.
RUNTIME_EXTRA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cm-002": ("신규상장 의무보유",),
    "cm-008": ("상장주선인의 의무인수",),
    "cm-012": ("질적심사요건",),
    "cm-015": ("주식매수선택권",),
    "cm-018": ("주식매수선택권 부여시가",),
    "cm-021": ("기업공개 준비 중인 주식",),
    "cm-024": ("주식등의 상장 등에 따른 이익의 증여",),
    "cm-038": ("내부회계관리제도",),
    "cm-048": ("우리사주조합원에 대한 주식 배정",),
    "cm-050": ("공동주관회사 선임의무",),
    "cm-051": ("공동주관회사 선임의무",),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dataset_digest() -> str:
    return hashlib.sha256(CM_PATH.read_bytes() + b"\0" + FSC_PATH.read_bytes()).hexdigest()


def _authority_evidence(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for surface in AUTHORITY_SURFACES:
        start = text.find(surface)
        if start >= 0:
            found.append((start, surface))
    found.extend((match.start(), match.group(0)) for match in ARTICLE_RE.finditer(text))
    out: list[str] = []
    for _start, value in sorted(found):
        if value not in out:
            out.append(value)
    return out


def _classify(text: str, keyword_evidence: Sequence[str]) -> dict[str, Any]:
    authority = _authority_evidence(text)
    keywords = list(dict.fromkeys(str(value) for value in keyword_evidence))
    for value in (*authority, *keywords):
        if not value or value not in text:
            raise ValueError(f"surface evidence is not an exact substring: {value!r}")
    authority_explicit = bool(authority)
    keyword_explicit = bool(keywords)
    label = (
        "authority-explicit"
        if authority_explicit
        else "keyword-explicit"
        if keyword_explicit
        else "latent-only"
    )
    return {
        "label": label,
        "authority_explicit": authority_explicit,
        "keyword_explicit": keyword_explicit,
        "authority_evidence": authority,
        "keyword_evidence": keywords,
    }


def _load_cases() -> list[dict[str, Any]]:
    if _sha256(CM_PATH) != CM_SHA256 or _sha256(FSC_PATH) != FSC_SHA256:
        raise ValueError("frozen source hash mismatch")
    if _dataset_digest() != DATASET_SHA256:
        raise ValueError("combined frozen dataset hash mismatch")
    cm = json.loads(CM_PATH.read_text(encoding="utf-8"))
    fsc = json.loads(FSC_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for source_name, raw in (("cm", cm), ("fsc-hard", fsc)):
        for row in raw.get("cases") or ():
            case = dict(row)
            case["dataset"] = source_name
            rows.append(case)
    ids = [str(row.get("id") or "") for row in rows]
    if len(rows) != 61 or len(set(ids)) != 61 or set(ids) != set(SOURCE_KEYWORDS):
        raise ValueError("frozen 61-case coverage mismatch")
    return rows


def _gold_counts(row: Mapping[str, Any]) -> tuple[int, int]:
    articles = list(row.get("expected_articles") or ())
    present = sum(1 for item in articles if item.get("corpus_status") == "present")
    return len(articles), present


def build_report(*, manifest_sha256: str) -> dict[str, Any]:
    cases = _load_cases()
    output_rows: list[dict[str, Any]] = []
    for row in cases:
        case_id = str(row["id"])
        runtime_question = str(row.get("question") or "")
        source_question = str(row.get("source_question") or runtime_question)
        source_keywords = SOURCE_KEYWORDS[case_id]
        runtime_keywords = (
            *source_keywords,
            *RUNTIME_EXTRA_KEYWORDS.get(case_id, ()),
        )
        source_result = _classify(source_question, source_keywords)
        runtime_result = _classify(runtime_question, runtime_keywords)
        declared_gold, present_gold = _gold_counts(row)
        output_rows.append(
            {
                "case_id": case_id,
                "dataset": row["dataset"],
                "source_question": source_question,
                "runtime_question": runtime_question,
                "injected_context": (
                    runtime_question[len(source_question):].strip()
                    if runtime_question.startswith(source_question)
                    else None
                ),
                "source_question_view": source_result,
                "runtime_question_view": runtime_result,
                "label_transition": (
                    f"{source_result['label']}->{runtime_result['label']}"
                ),
                "label_changed": source_result["label"] != runtime_result["label"],
                "declared_gold_articles": declared_gold,
                "corpus_present_gold_articles": present_gold,
            }
        )

    def summarize(view: str) -> dict[str, Any]:
        by_label: dict[str, dict[str, int]] = {}
        for label in LABELS:
            selected = [row for row in output_rows if row[view]["label"] == label]
            by_label[label] = {
                "cases": len(selected),
                "declared_gold_articles": sum(row["declared_gold_articles"] for row in selected),
                "corpus_present_gold_articles": sum(
                    row["corpus_present_gold_articles"] for row in selected
                ),
            }
        overlap = Counter()
        for row in output_rows:
            cell = row[view]
            key = (
                "authority_and_keyword"
                if cell["authority_explicit"] and cell["keyword_explicit"]
                else "authority_only"
                if cell["authority_explicit"]
                else "keyword_only"
                if cell["keyword_explicit"]
                else "neither"
            )
            overlap[key] += 1
        return {"by_label": by_label, "overlap_cases": dict(sorted(overlap.items()))}

    transitions = Counter(row["label_transition"] for row in output_rows)
    summary = {
        "cases": len(output_rows),
        "declared_gold_articles": sum(row["declared_gold_articles"] for row in output_rows),
        "corpus_present_gold_articles": sum(
            row["corpus_present_gold_articles"] for row in output_rows
        ),
        "source_question_view": summarize("source_question_view"),
        "runtime_question_view": summarize("runtime_question_view"),
        "label_transitions": dict(sorted(transitions.items())),
        "label_changed_cases": sum(row["label_changed"] for row in output_rows),
        "injected_context_cases": sum(bool(row["injected_context"]) for row in output_rows),
    }
    for view in ("source_question_view", "runtime_question_view"):
        if sum(v["cases"] for v in summary[view]["by_label"].values()) != 61:
            raise ValueError(f"label partition does not span 61 cases: {view}")
        if sum(summary[view]["overlap_cases"].values()) != 61:
            raise ValueError(f"overlap matrix does not span 61 cases: {view}")
    if summary["declared_gold_articles"] != 85 or summary["corpus_present_gold_articles"] != 83:
        raise ValueError("gold instance denominator mismatch")

    report: dict[str, Any] = {
        "schema_version": "golden-question-surface-strata-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "classification_precedence": list(LABELS),
        "gold_visible_to_classifier": False,
        "legal_article_bodies_visible_to_classifier": False,
        "llm_calls": 0,
        "retrieval_calls": 0,
        "main_wiring": "unchanged",
        "source_lineage": {
            "cm_path": str(CM_PATH.relative_to(ROOT)),
            "cm_sha256": CM_SHA256,
            "fsc_path": str(FSC_PATH.relative_to(ROOT)),
            "fsc_sha256": FSC_SHA256,
            "combined_sha256": DATASET_SHA256,
            "manifest_path": str(MANIFEST.relative_to(ROOT)),
            "manifest_sha256": manifest_sha256,
        },
        "summary": summary,
        "rows": output_rows,
    }
    report["artifact_sha256"] = _json_digest(report)
    return report


def _validate_manifest(path: Path, expected_sha256: str) -> str:
    if not expected_sha256 or expected_sha256 == "PENDING":
        raise ValueError("a frozen manifest SHA-256 is required")
    actual = _sha256(path)
    if actual != expected_sha256:
        raise ValueError(f"manifest hash mismatch: expected={expected_sha256} actual={actual}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID or manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("ADR or experiment id mismatch")
    design = manifest.get("design") or {}
    if design.get("criteria_frozen_before_run") is not True:
        raise ValueError("criteria are not frozen")
    if (design.get("surface_stratification_contract") or {}).get("schema_version") \
            != "golden-question-surface-strata-v1":
        raise ValueError("surface classification contract mismatch")
    if (manifest.get("llm_policy") or {}).get("llm_calls") != []:
        raise ValueError("this audit must declare zero LLM calls")
    stage = (manifest.get("retrieval_accounting") or {}).get("stage_ledger") or {}
    if stage.get("mode") != "not_applicable":
        raise ValueError("retrieval stage mode must be not_applicable")
    runs = {row.get("id"): row for row in manifest.get("runs") or ()}
    run = runs.get(RUN_ID) or {}
    if run.get("status") not in {"planned", "running", "complete"}:
        raise ValueError("run-001 is not executable")
    if run.get("artifact_path") != str(OUTPUT.relative_to(ROOT)):
        raise ValueError("artifact path mismatch")
    frozen_runner = run.get("runner_sha256")
    if frozen_runner and frozen_runner != _sha256(Path(__file__).resolve()):
        raise ValueError("runner hash mismatch")
    frozen_tests = run.get("test_sha256") or {}
    if not frozen_tests:
        raise ValueError("test hash gate is missing")
    for relative, digest in frozen_tests.items():
        candidate = (ROOT / str(relative)).resolve()
        if ROOT != candidate and ROOT not in candidate.parents:
            raise ValueError("test hash path escapes repository")
        if not candidate.is_file() or _sha256(candidate) != digest:
            raise ValueError(f"test hash mismatch: {relative}")
    return actual


def _write(path: Path, report: Mapping[str, Any]) -> tuple[str, int]:
    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    manifest_sha = _validate_manifest(args.manifest.resolve(), args.manifest_sha256)
    report = build_report(manifest_sha256=manifest_sha)
    summary = report["summary"]
    if args.validate_only:
        print(json.dumps({"status": "valid", "summary": summary}, ensure_ascii=False, sort_keys=True))
        return 0
    digest, size = _write(args.output.resolve(), report)
    print(json.dumps({"status": "complete", "sha256": digest, "bytes": size, "summary": summary}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
