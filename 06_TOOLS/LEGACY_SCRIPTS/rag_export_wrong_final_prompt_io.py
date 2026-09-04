#!/usr/bin/env python3
"""오답 사례의 최종 rag.answer 입력을 재구성하고 원출력을 사람용 파일로 내보낸다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import switches, wikictx  # noqa: E402
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_product_request(question: str, sections: list[answer_mod.Section],
                          spots: list[dict] | None = None) -> dict[str, Any]:
    """answer.synthesize의 최종 structured 호출 직전 값을 모델 호출 없이 만든다."""
    picks = list(spots or [])
    if switches.is_on("wiki_context"):
        have = {str(pick.get("slug") or "") for pick in picks}
        for pick in wikictx.methods_for(sections):
            if pick["slug"] not in have:
                picks.append(pick)
                have.add(pick["slug"])
        picks += [pick for pick in wikictx.pick(question, {section.doc for section in sections})
                  if pick["slug"] not in have]
    user = (f"[질문]\n{question}\n\n[컨텍스트]\n"
            f"{answer_mod._context_text(sections)}" + wikictx.block(picks))
    return {
        "call_name": "rag.answer",
        "system": answer_mod.ANSWER_SYSTEM,
        "user": user,
        "schema": answer_mod.ANSWER_SCHEMA,
        "max_tokens": 4000,
        "effort": "high",
        "wiki_context_on": switches.is_on("wiki_context"),
        "wiki_picks": [{"slug": pick.get("slug"), "title": pick.get("title"),
                         "why": pick.get("why")} for pick in picks],
    }


def _fence(value: str, language: str = "text") -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}{language}\n{value}\n{marker}"


def _json_fence(value: Any) -> str:
    return _fence(json.dumps(value, ensure_ascii=False, indent=2), "json")


def case_markdown(row: dict[str, Any]) -> str:
    request = row["final_product_request"]
    output = row["original_product_output"]
    selected = row["selected_evidence"]
    lines = [
        f"# {row['case_no']} — 오답 최종 prompt 입출력",
        "",
        "> 보존 범위: 최종 제품 호출 `rag.answer`만 포함한다. 의미 채점 prompt는 제품",
        "> 답변 생성 입력이 아니므로 포함하지 않았다. 출력은 원 실행 artifact 값이다.",
        "> 입력 문자열은 원 artifact에 저장되지 않아, 동결 선택 좌표와 현재 동일",
        "> `answer.synthesize` 조립 코드·코퍼스·Wiki 설정으로 모델 호출 없이 재구성했다.",
        "",
        "## 실행 정보",
        "",
        "| 필드 | 값 |",
        "|---|---|",
        f"| 모델 | `{row['model']}` |",
        f"| 호출명 | `{request['call_name']}` |",
        f"| max tokens | `{request['max_tokens']}` |",
        f"| effort | `{request['effort']}` |",
        f"| 선택 근거 | `{len(selected)}개` |",
        f"| Wiki context | `{request['wiki_context_on']}` |",
        f"| 원 input tokens | `{row['original_usage'].get('input_tokens', 0):,}` |",
        f"| 원 output tokens | `{row['original_usage'].get('output_tokens', 0):,}` |",
        f"| system SHA-256 | `{row['hashes']['system_sha256']}` |",
        f"| user SHA-256 | `{row['hashes']['user_sha256']}` |",
        "",
        "## 질문",
        "",
        _fence(row["question"]),
        "",
        "## 기준답변 — 제품 prompt에는 들어가지 않음",
        "",
        _fence(row["reference_answer"]),
        "",
        "## 의미 채점 결과 — 제품 prompt에는 들어가지 않음",
        "",
        _json_fence(row["semantic_grade"]),
        "",
        "## 선택된 최종 근거 좌표",
        "",
        _json_fence(selected),
        "",
        "## 최종 제품 입력: system",
        "",
        _fence(request["system"]),
        "",
        "## 최종 제품 입력: user — 전체 원문, 생략 없음",
        "",
        _fence(request["user"]),
        "",
        "## 최종 제품 입력: structured-output schema",
        "",
        _json_fence(request["schema"]),
        "",
        "## 원 실행의 파싱된 structured output",
        "",
        _json_fence(output),
        "",
        "## 원 최종 답변 문자열",
        "",
        _fence(output["answer"]),
        "",
    ]
    return "\n".join(lines)


def index_markdown(rows: list[dict[str, Any]], *, json_path: Path,
                   source_answers: Path, source_retrieval: Path) -> str:
    total_chars = sum(len(row["final_product_request"]["user"]) for row in rows)
    lines = [
        "# CM Core 오답 16건 — 최종 prompt 입출력 감사",
        "",
        "대표 실행 `control_d_then_verifier`의 의미 오답 사례만 분리했다.",
        "각 사례 파일에는 최종 `rag.answer`의 system, user, schema와 원 실행의",
        "파싱된 structured output을 생략 없이 기록했다.",
        "",
        "## 보존 한계",
        "",
        "원 실행 artifact는 API prompt 문자열과 provider raw bytes를 저장하지 않았다.",
        "따라서 출력 값은 원 artifact 그대로이며, 입력은 동결 선택 좌표를 현재 동일",
        "합성 코드·코퍼스·Wiki 설정으로 재구성한 값이다. 향후 실행은 원 prompt와 raw",
        "응답을 호출 시점에 직접 저장해야 완전한 byte-for-byte 감사를 할 수 있다.",
        "",
        "## 요약",
        "",
        "| 항목 | 값 |",
        "|---|---:|",
        f"| 오답 사례 | {len(rows)} |",
        f"| 재구성 user prompt 총 문자 | {total_chars:,} |",
        f"| 입력 source | `{source_answers}` |",
        f"| 회수 source | `{source_retrieval}` |",
        f"| 전체 기계 원장 | `{json_path}` |",
        "",
        "## 사례 목록",
        "",
        "| 사례 | 질문 | 근거 수 | input tokens | 파일 |",
        "|---|---|---:|---:|---|",
    ]
    for row in rows:
        question = " ".join(row["question"].split())
        if len(question) > 90:
            question = question[:87] + "…"
        lines.append(
            f"| {row['case_no']} | {question} | {len(row['selected_evidence'])} | "
            f"{int(row['original_usage'].get('input_tokens') or 0):,} | "
            f"[{row['case_no']}.md]({row['case_no']}.md) |")
    lines += ["", "## 무결성", "",
              "- 원답변 문자열과 export output의 일치 여부는 생성 스크립트가 검사한다.",
              "- 오답 수가 16건이 아니면 기본 실행은 실패한다.",
              "- 제품 prompt에는 기준답변·의미 채점 결과를 넣지 않는다.", ""]
    return "\n".join(lines)


def export(args) -> dict[str, Any]:
    suite = json.loads(args.suite.read_text("utf-8"))
    answers = json.loads(args.answers.read_text("utf-8"))
    retrieval = json.loads(args.retrieval.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieval_rows = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    index = index_mod.current()
    rows = []
    for source in answers.get("rows") or []:
        variant = (source.get("variants") or {}).get(args.variant) or {}
        if variant.get("error") or bool(variant.get("semantic_correct")):
            continue
        case_id = str(source.get("case_no") or "")
        case = cases[case_id]
        selected = (((retrieval_rows[case_id].get("variants") or {})
                     .get(args.variant) or {}).get("selected") or [])
        evidence = reconstruct_evidence(index, selected)
        sections = _sections(evidence)
        request = build_product_request(str(case.get("question") or ""), sections, spots=[])
        output = {"answer": str(variant.get("answer") or ""),
                  "answerable": bool(variant.get("answerable"))}
        if output["answer"] != str(variant.get("answer") or ""):
            raise RuntimeError(f"{case_id}: original answer mismatch")
        rows.append({
            "case_no": case_id,
            "model": str(answers.get("system_model") or ""),
            "question": str(case.get("question") or ""),
            "reference_answer": str(case.get("reference_answer") or ""),
            "semantic_grade": variant.get("semantic_grade") or {},
            "selected_evidence": list(selected),
            "reconstructed_evidence": evidence,
            "final_product_request": request,
            "original_product_output": output,
            "original_usage": variant.get("usage") or {},
            "hashes": {
                "system_sha256": sha256_text(request["system"]),
                "user_sha256": sha256_text(request["user"]),
                "output_answer_sha256": sha256_text(output["answer"]),
            },
        })
    expected = int(args.expected_wrong)
    if len(rows) != expected:
        raise RuntimeError(f"wrong row count: {len(rows)} != {expected}")
    result = {
        "experiment": "wrong-final-prompt-io-export-v1",
        "contract": {
            "model_called": False,
            "product_output_source": "original answer artifact, parsed values",
            "product_input_source": (
                "deterministically reconstructed from frozen selection coordinates, "
                "current answer.synthesize prompt builder, corpus, and wiki settings"),
            "raw_provider_response_available": False,
            "semantic_gold_in_product_prompt": False,
            "no_prompt_truncation": True,
            "main_wiring_changed": False,
            "canonical_changed": False,
        },
        "sources": {"suite": str(args.suite), "answers": str(args.answers),
                    "retrieval": str(args.retrieval), "variant": args.variant},
        "summary": {
            "wrong_cases": len(rows),
            "user_prompt_chars": sum(len(row["final_product_request"]["user"])
                                     for row in rows),
            "selected_evidence_presentations": sum(len(row["selected_evidence"])
                                                   for row in rows),
            "original_input_tokens": sum(int(row["original_usage"].get("input_tokens") or 0)
                                         for row in rows),
            "original_output_tokens": sum(int(row["original_usage"].get("output_tokens") or 0)
                                          for row in rows),
        },
        "rows": rows,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-dir", type=Path, required=True)
    parser.add_argument("--expected-wrong", type=int, default=16)
    args = parser.parse_args()
    result = export(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_dir.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    for row in result["rows"]:
        (args.markdown_dir / f"{row['case_no']}.md").write_text(
            case_markdown(row), "utf-8")
    (args.markdown_dir / "README.md").write_text(index_markdown(
        result["rows"], json_path=args.json_out,
        source_answers=args.answers, source_retrieval=args.retrieval), "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
