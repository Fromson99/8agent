#!/usr/bin/env python3
"""ADR-0040: 같은 고정 회수 좌표에서 조문 원문과 Frame-only 표현을 Haiku A/B한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 저장소 환경을 먼저 고정한다.
from lawrag.core.rag import answer, frames, legal_coordinates, switches, wikictx  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.rag_definition_context_answer_ab import (  # noqa: E402
    HAIKU, JUDGE_SCHEMA, JUDGE_SYSTEM,
)
from scripts.rag_legal_issue_e2e_eval import _percentile, _usage  # noqa: E402


ADR_DIR = ROOT / "docs/adr/ADR-0040-frame-only-legal-answer-ab"
RAW_DEFAULT = ROOT / "var/eval/e2e/ADR-0040/frame_only_answer_ab_51.json"
FRAME_FIELDS = ("actor", "act", "target", "object", "mode", "function")


def _is_descendant(view, node, root) -> bool:
    seen = set()
    while node is not None and node not in seen:
        if node == root:
            return True
        seen.add(node)
        node = (view.by_id.get(node) or {}).get("parent")
    return False


def frames_for_section(view, node) -> list[dict]:
    """선택 구역 자신/자손에 source 좌표가 있는 Frame만 순서대로 반환한다."""
    out = []
    for row in frames.load(view.doc_id):
        if (_is_descendant(view, row.get("node"), node)
                or _is_descendant(view, row.get("jo"), node)):
            out.append(row)
    return out


def render_frames(view, node, rows: list[dict]) -> str:
    """원문을 한 글자도 보태지 않고 기존 Frame 필드만 사람이 읽게 렌더링한다."""
    if not rows:
        return "[구조화 프레임 없음 — 이 회수 구역의 조문 원문은 제공되지 않음]"
    parts = [
        "[조문 원문 대신 제공된 구조화 프레임]",
        "각 행은 기존 추출 데이터다. 빈 문자열은 추출값 없음, 단서=true는 단서문이다.",
    ]
    for position, row in enumerate(rows, 1):
        source_node = row.get("node") if row.get("node") is not None else row.get("jo")
        source_path = view.path(source_node) or view.path(row.get("jo"))
        parts.append(
            f"\n프레임 {position}\n"
            f"- 출처 마디: {source_path}\n"
            f"- actor(규율 주체): {row.get('actor') or '(없음)'}\n"
            f"- act(행위·술어): {row.get('act') or '(없음)'}\n"
            f"- target(상대방): {row.get('target') or '(없음)'}\n"
            f"- object(행위 객체): {row.get('object') or '(없음)'}\n"
            f"- mode(문형): {row.get('mode') or '(없음)'}\n"
            f"- function(규범 기능): {row.get('function') or '(없음)'}\n"
            f"- 단서: {'true' if row.get('proviso') else 'false'}"
        )
    return "\n".join(parts)


def sections(index, selected: list[dict], representation: str) -> tuple[list[Section], dict]:
    out = []
    original_chars = frame_chars = frame_count = covered = 0
    no_frame = []
    for position, item in enumerate(selected, 1):
        view = index.docs[item["doc_id"]]
        original = legal_coordinates.subtree_text(view, item["node"], cap=None)
        frame_rows = frames_for_section(view, item["node"])
        rendered = render_frames(view, item["node"], frame_rows)
        original_chars += len(original)
        frame_chars += len(rendered)
        frame_count += len(frame_rows)
        covered += int(bool(frame_rows))
        if not frame_rows:
            no_frame.append({"doc_id": item["doc_id"], "node": item["node"],
                             "doc": item["doc"], "path": item["path"]})
        out.append(Section(
            n=position, doc_id=item["doc_id"], doc=item["doc"], node=item["node"],
            path=item["path"], page=(view.by_id.get(item["node"]) or {}).get("page"),
            kind="법률좌표폐쇄", matched=item.get("origin") or "frozen",
            text=original if representation == "original" else rendered))
    return out, {
        "selected_sections": len(selected), "sections_with_frames": covered,
        "section_frame_coverage": round(covered / len(selected), 4) if selected else 0,
        "frame_count": frame_count, "original_body_chars": original_chars,
        "frame_render_chars": frame_chars, "no_frame_sections": no_frame,
    }


def _prompt(question: str, sections_: list[Section]) -> tuple[str, list[dict]]:
    """answer.synthesize와 같은 결정론 조립을 하되 실제 전송 문자열을 보존한다."""
    picks = []
    if switches.is_on("wiki_context"):
        have = set()
        for pick in wikictx.methods_for(sections_):
            if pick["slug"] not in have:
                picks.append(pick)
                have.add(pick["slug"])
        for pick in wikictx.pick(question, {section.doc for section in sections_}):
            if pick["slug"] not in have:
                picks.append(pick)
                have.add(pick["slug"])
    user = (f"[질문]\n{question}\n\n[컨텍스트]\n{answer._context_text(sections_)}"
            + answer._definition_context_text(sections_) + wikictx.block(picks))
    public_picks = [{"slug": p["slug"], "title": p["title"], "why": p["why"]}
                    for p in picks]
    return user, public_picks


def _generate(llm, call_name: str, question: str, sections_: list[Section]) -> dict:
    user, picks = _prompt(question, sections_)
    log0 = len(llm.log)
    started = time.perf_counter()
    out = llm.structured(call_name, answer.ANSWER_SYSTEM, user, answer.ANSWER_SCHEMA,
                         max_tokens=4000, effort="high", model=HAIKU)
    wall_ms = round((time.perf_counter() - started) * 1000)
    usage = _usage(list(llm.log)[log0:])
    if out is None or not out.get("answer"):
        error = llm.log[-1].error if llm.log else "empty answer"
        raise RuntimeError(str(error))
    return {
        "system_prompt": answer.ANSWER_SYSTEM, "user_prompt": user,
        "answer": str(out["answer"]), "answerable": bool(out.get("answerable")),
        "wiki": picks, "usage": usage, "wall_ms": wall_ms,
        "prompt_chars": len(answer.ANSWER_SYSTEM) + len(user),
    }


def _summary(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    original = sum(row["judge"]["original"]["correct"] for row in good)
    frame_only = sum(row["judge"]["frame_only"]["correct"] for row in good)
    coverage_sections = sum(row["coverage"]["selected_sections"] for row in good)
    coverage_hit = sum(row["coverage"]["sections_with_frames"] for row in good)
    result = {
        "cases": len(rows), "completed": len(good),
        "original_correct": original,
        "original_accuracy": round(original / len(good), 4) if good else 0,
        "frame_only_correct": frame_only,
        "frame_only_accuracy": round(frame_only / len(good), 4) if good else 0,
        "delta": frame_only - original,
        "paired": {
            "both_correct": sum(row["judge"]["original"]["correct"]
                                and row["judge"]["frame_only"]["correct"] for row in good),
            "original_only": sum(row["judge"]["original"]["correct"]
                                 and not row["judge"]["frame_only"]["correct"] for row in good),
            "frame_only_only": sum(not row["judge"]["original"]["correct"]
                                   and row["judge"]["frame_only"]["correct"] for row in good),
            "both_incorrect": sum(not row["judge"]["original"]["correct"]
                                  and not row["judge"]["frame_only"]["correct"] for row in good),
        },
        "coverage": {
            "selected_sections": coverage_sections,
            "sections_with_frames": coverage_hit,
            "section_frame_coverage": round(coverage_hit / coverage_sections, 4)
            if coverage_sections else 0,
            "cases_with_any_frame": sum(row["coverage"]["sections_with_frames"] > 0
                                        for row in good),
            "cases_with_all_sections_framed": sum(
                row["coverage"]["sections_with_frames"]
                == row["coverage"]["selected_sections"] for row in good),
            "frames": sum(row["coverage"]["frame_count"] for row in good),
        },
    }
    for name in ("original", "frame_only"):
        walls = [row[name]["wall_ms"] for row in good]
        result[name] = {
            "usage": {key: sum(row[name]["usage"][key] for row in good)
                      for key in ("calls", "input_tokens", "output_tokens",
                                  "duration_ms", "errors")},
            "prompt_chars": sum(row[name]["prompt_chars"] for row in good),
            "wall_ms_p50": _percentile(walls, .5),
            "wall_ms_p95": _percentile(walls, .95),
            "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        }
    result["input_token_reduction"] = round(
        1 - result["frame_only"]["usage"]["input_tokens"]
        / result["original"]["usage"]["input_tokens"], 4)
    return result


def _write_cases(blob: dict) -> dict:
    cases_dir = ADR_DIR / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"files": []}
    for number, row in enumerate(blob["rows"], 1):
        case_no = row["case_no"]
        path = cases_dir / f"{number:03d}-{case_no}.md"
        if row.get("error"):
            text = f"# {case_no}\n\n실험 오류: `{row['error']}`\n"
        else:
            cov = row["coverage"]
            text = (
                f"# {case_no} — 원문 vs Frame-only\n\n"
                f"## 질문\n\n{row['question']}\n\n"
                f"## 사람 기준답변(채점자에게만 제공)\n\n{row['reference_answer']}\n\n"
                f"## 고정 회수 및 Frame coverage\n\n"
                f"- 회수 구역: {cov['selected_sections']}\n"
                f"- Frame 보유 구역: {cov['sections_with_frames']} "
                f"({cov['section_frame_coverage']:.1%})\n"
                f"- Frame 행: {cov['frame_count']}\n"
                f"- 원문 본문 문자: {cov['original_body_chars']:,}\n"
                f"- Frame 렌더 문자: {cov['frame_render_chars']:,}\n\n"
                f"### Frame 없는 회수 구역\n\n"
                + ("\n".join(f"- {x['doc']} ▸ {x['path']}" for x in cov["no_frame_sections"])
                   or "- 없음")
                + "\n\n## 원문 arm — 실제 제품 입력\n\n"
                f"### system\n\n```text\n{row['original']['system_prompt']}\n```\n\n"
                f"### user\n\n```text\n{row['original']['user_prompt']}\n```\n\n"
                f"### 제품 출력\n\n{row['original']['answer']}\n\n"
                f"- usage: `{json.dumps(row['original']['usage'], ensure_ascii=False)}`\n"
                f"- wall_ms: {row['original']['wall_ms']}\n\n"
                f"## Frame-only arm — 실제 제품 입력\n\n"
                f"### system\n\n```text\n{row['frame_only']['system_prompt']}\n```\n\n"
                f"### user\n\n```text\n{row['frame_only']['user_prompt']}\n```\n\n"
                f"### 제품 출력\n\n{row['frame_only']['answer']}\n\n"
                f"- usage: `{json.dumps(row['frame_only']['usage'], ensure_ascii=False)}`\n"
                f"- wall_ms: {row['frame_only']['wall_ms']}\n\n"
                f"## Haiku paired judge — 실제 입력\n\n"
                f"### system\n\n```text\n{row['judge_system_prompt']}\n```\n\n"
                f"### user\n\n```text\n{row['judge_user_prompt']}\n```\n\n"
                f"### 구조화 출력\n\n```json\n"
                f"{json.dumps(row['judge_raw'], ensure_ascii=False, indent=2)}\n```\n\n"
                f"### 정규화 판정\n\n"
                f"- original: `{json.dumps(row['judge']['original'], ensure_ascii=False)}`\n"
                f"- frame_only: `{json.dumps(row['judge']['frame_only'], ensure_ascii=False)}`\n"
            )
        path.write_text(text, "utf-8")
        manifest["files"].append({
            "case_no": case_no, "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    index_lines = [
        "# ADR-0040 질문별 실제 입출력", "",
        "원문 arm과 Frame-only arm의 실제 system/user prompt, 출력, Haiku paired judge를 보존한다.", "",
    ]
    for item in manifest["files"]:
        index_lines.append(f"- [{item['case_no']}]({Path(item['path']).name})")
    readme = cases_dir / "README.md"
    readme.write_text("\n".join(index_lines) + "\n", "utf-8")
    manifest["readme_sha256"] = hashlib.sha256(readme.read_bytes()).hexdigest()
    manifest_path = cases_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"directory": str(cases_dir.relative_to(ROOT)), "files": len(manifest["files"]),
            "manifest": str(manifest_path.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", type=Path,
                        default=ROOT / "var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json")
    parser.add_argument("--answers", type=Path,
                        default=ROOT / "var/eval/e2e/cm_core_legalclosure_stage_answer_ab_51.json")
    parser.add_argument("--out", type=Path, default=RAW_DEFAULT)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--cases", default="")
    parser.add_argument("--coverage-only", action="store_true")
    args = parser.parse_args()

    stage_blob = json.loads(args.stage.read_text("utf-8"))
    answers_by_case = {row["case_no"]: row
                       for row in json.loads(args.answers.read_text("utf-8"))["rows"]}
    wanted = {item.strip() for item in args.cases.split(",") if item.strip()}
    sources = [row for row in stage_blob["rows"] if not wanted or row["case_no"] in wanted]
    index = index_mod.current().scoped(None)

    coverage_rows = []
    for source in sources:
        selected = source["variants"]["control_d_then_verifier"]["selected"]
        _, coverage = sections(index, selected, "frame_only")
        coverage_rows.append({"case_no": source["case_no"], **coverage})
    coverage_summary = {
        "cases": len(coverage_rows),
        "selected_sections": sum(r["selected_sections"] for r in coverage_rows),
        "sections_with_frames": sum(r["sections_with_frames"] for r in coverage_rows),
        "frames": sum(r["frame_count"] for r in coverage_rows),
        "cases_with_any_frame": sum(r["sections_with_frames"] > 0 for r in coverage_rows),
        "cases_with_all_sections_framed": sum(
            r["sections_with_frames"] == r["selected_sections"] for r in coverage_rows),
    }
    coverage_summary["section_frame_coverage"] = round(
        coverage_summary["sections_with_frames"] / coverage_summary["selected_sections"], 4)
    if args.coverage_only:
        print(json.dumps({"summary": coverage_summary, "rows": coverage_rows},
                         ensure_ascii=False, indent=1))
        return 0

    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU:
        raise SystemExit(f"모든 LLM은 {HAIKU}여야 합니다: {getattr(prototype, 'model', None)}")
    local = threading.local()

    def evaluate(source):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm is None or local.llm.model != HAIKU:
                raise RuntimeError("worker model is not Haiku")
        llm = local.llm
        case_no, question = source["case_no"], source["question"]
        selected = source["variants"]["control_d_then_verifier"]["selected"]
        original_sections, coverage = sections(index, selected, "original")
        frame_sections, _ = sections(index, selected, "frame_only")
        product_order = ("frame_only", "original") if int(case_no[-3:]) % 2 == 0 \
            else ("original", "frame_only")
        section_map = {"original": original_sections, "frame_only": frame_sections}
        generated = {}
        for name in product_order:
            generated[name] = _generate(
                llm, f"eval.adr0040.answer.{name}", question, section_map[name])
        reference = answers_by_case[case_no]["reference_answer"]
        # 제품 호출 순서의 반대로 judge A/B를 두어 고정 위치 편향도 교차한다.
        a_name, b_name = product_order[1], product_order[0]
        judge_user = (f"[기준답변]\n{reference}\n\n"
                      f"[답변 A]\n{generated[a_name]['answer']}\n\n"
                      f"[답변 B]\n{generated[b_name]['answer']}")
        j0 = len(llm.log)
        judged = llm.structured(
            "eval.adr0040.paired", JUDGE_SYSTEM, judge_user, JUDGE_SCHEMA,
            max_tokens=1400, effort="medium", model=HAIKU)
        judge_usage = _usage(list(llm.log)[j0:])
        if judged is None:
            raise RuntimeError("paired judge failed")
        labels = {a_name: "A", b_name: "B"}
        normalized = {
            name: {"correct": bool(judged[labels[name]]["correct"]),
                   "reason": str(judged[labels[name]]["reason"])[:800]}
            for name in ("original", "frame_only")
        }
        return {
            "case_no": case_no, "question": question, "reference_answer": reference,
            "selected": selected, "coverage": coverage,
            "original": generated["original"], "frame_only": generated["frame_only"],
            "product_order": list(product_order), "judge_order": labels,
            "judge_system_prompt": JUDGE_SYSTEM, "judge_user_prompt": judge_user,
            "judge_raw": judged, "judge": normalized, "judge_usage": judge_usage,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows, positions = [], {row["case_no"]: i for i, row in enumerate(sources)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): row["case_no"] for row in sources}
        for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_no = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_no, "question": next(
                    source["question"] for source in sources if source["case_no"] == case_no),
                    "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda item: positions[item["case_no"]])
            partial = {
                "experiment": "ADR-0040-frame-only-legal-answer-fresh-fresh-ab",
                "model_contract": {"original": HAIKU, "frame_only": HAIKU, "judge": HAIKU},
                "frozen_retrieval": str(args.stage.relative_to(ROOT)),
                "summary": _summary(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(partial, ensure_ascii=False, indent=1) + "\n", "utf-8")
            marks = row.get("judge") or {}
            print(f"[{number:02d}/{len(sources)}] {case_no} "
                  f"O={'○' if (marks.get('original') or {}).get('correct') else '✗'} "
                  f"F={'○' if (marks.get('frame_only') or {}).get('correct') else '✗'}",
                  flush=True)

    result = json.loads(args.out.read_text("utf-8"))
    result["case_markdown"] = _write_cases(result)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
