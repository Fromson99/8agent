#!/usr/bin/env python3
"""ADR-0041: 전체 정의조, 조문별 inline 정의, 정의 없음의 Haiku fresh ABC."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402
from lawrag.core.rag import answer, definitions, legal_coordinates, switches, wikictx  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments import inline_definition_cards as cards  # noqa: E402
from scripts.rag_definition_context_answer_ab import HAIKU  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import _percentile, _usage  # noqa: E402


VARIANTS = ("raw_definition_articles", "inline_same_doc", "no_definitions")
ADR_DIR = ROOT / "docs/adr/ADR-0041-definition-knowledge-card"
OUT_DEFAULT = ROOT / "var/eval/e2e/ADR-0041/inline_definition_card_answer_abc_51.json"

JUDGE_SYSTEM = (
    "너는 법률 E2E 답변의 동일 기준 비교 채점자다. 기준답변은 사람이 확정한 정답이다. "
    "답변 A, B, C를 각각 독립적으로 채점한다. 핵심 결론·조건·예외·수치가 기준답변과 "
    "일치하고 중요한 누락이나 모순이 없을 때만 correct=true다. 다른 답변과 상대 비교하지 "
    "말고 각 답변을 기준답변에 직접 비교한다. 관련 설명은 허용하지만 다른 규범을 "
    "지배규범처럼 섞거나 근거가 있는데도 회피하면 false다."
)
JUDGE_SCHEMA = {
    "type": "object", "properties": {
        label: {"type": "object", "properties": {
            "correct": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["correct", "reason"], "additionalProperties": False}
        for label in ("A", "B", "C")
    }, "required": ["A", "B", "C"], "additionalProperties": False,
}


def build_sections(index, selected: list[dict], variant: str) -> tuple[list[Section], dict]:
    out, dropped, card_rows = [], [], []
    body_chars = card_chars = 0
    for item in selected:
        view = index.docs[item["doc_id"]]
        if variant != "raw_definition_articles" \
                and definitions.is_definition_node(view, item["node"]):
            dropped.append(item)
            continue
        body = legal_coordinates.subtree_text(view, item["node"], cap=None)
        body_chars += len(body)
        matched = cards.matching_definitions(index, item["doc_id"], item["node"]) \
            if variant == "inline_same_doc" else []
        rendered = cards.render(matched)
        card_chars += len(rendered)
        card_rows.extend({"provision_doc_id": item["doc_id"],
                          "provision_node": item["node"],
                          "provision_path": item["path"], **row}
                         for row in matched)
        out.append(Section(
            n=len(out) + 1, doc_id=item["doc_id"], doc=item["doc"], node=item["node"],
            path=item["path"], page=(view.by_id.get(item["node"]) or {}).get("page"),
            kind="법률좌표폐쇄", matched=item.get("origin") or "frozen",
            text=body + rendered))
    return out, {
        "selected_sections": len(out), "dropped_definition_sections": dropped,
        "dropped_definition_count": len(dropped), "definition_cards": card_rows,
        "definition_card_count": len(card_rows), "body_chars": body_chars,
        "definition_card_chars": card_chars,
        "context_chars": body_chars + card_chars,
    }


def _wiki_picks(question: str, sections_: list[Section]) -> list[dict]:
    picks = []
    if not switches.is_on("wiki_context"):
        return picks
    have = set()
    for pick in wikictx.methods_for(sections_):
        if pick["slug"] not in have:
            picks.append(pick)
            have.add(pick["slug"])
    for pick in wikictx.pick(question, {section.doc for section in sections_}):
        if pick["slug"] not in have:
            picks.append(pick)
            have.add(pick["slug"])
    return picks


def _prompt(question: str, sections_: list[Section], picks: list[dict]) -> str:
    return (f"[질문]\n{question}\n\n[컨텍스트]\n{answer._context_text(sections_)}"
            + wikictx.block(picks))


def _generate(llm, name: str, system: str, user: str) -> dict:
    log0 = len(llm.log)
    started = time.perf_counter()
    out = llm.structured(f"eval.adr0041.answer.{name}", system, user,
                         answer.ANSWER_SCHEMA, max_tokens=4000,
                         effort="high", model=HAIKU)
    wall_ms = round((time.perf_counter() - started) * 1000)
    usage = _usage(list(llm.log)[log0:])
    if out is None or not out.get("answer"):
        raise RuntimeError((llm.log[-1].error if llm.log else "empty answer") or "empty")
    return {"system_prompt": system, "user_prompt": user,
            "answer": str(out["answer"]), "answerable": bool(out.get("answerable")),
            "usage": usage, "wall_ms": wall_ms,
            "prompt_chars": len(system) + len(user)}


def _orders(case_no: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    number = int(case_no[-3:]) % 3
    product = VARIANTS[number:] + VARIANTS[:number]
    judge = tuple(reversed(product))
    return product, judge


def _summary(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    result = {"cases": len(rows), "completed": len(good), "variants": {}}
    for name in VARIANTS:
        correct = sum(row["judge"][name]["correct"] for row in good)
        walls = [row[name]["wall_ms"] for row in good]
        result["variants"][name] = {
            "correct": correct,
            "accuracy": round(correct / len(good), 4) if good else 0,
            "usage": {key: sum(row[name]["usage"][key] for row in good)
                      for key in ("calls", "input_tokens", "output_tokens",
                                  "duration_ms", "errors")},
            "prompt_chars": sum(row[name]["prompt_chars"] for row in good),
            "wall_ms_p50": _percentile(walls, .5),
            "wall_ms_p95": _percentile(walls, .95),
            "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        }
    result["patterns"] = {
        "all_correct": sum(all(row["judge"][n]["correct"] for n in VARIANTS)
                           for row in good),
        "all_incorrect": sum(not any(row["judge"][n]["correct"] for n in VARIANTS)
                             for row in good),
        "raw_only": sum(row["judge"][VARIANTS[0]]["correct"]
                        and not row["judge"][VARIANTS[1]]["correct"]
                        and not row["judge"][VARIANTS[2]]["correct"] for row in good),
        "inline_only": sum(not row["judge"][VARIANTS[0]]["correct"]
                           and row["judge"][VARIANTS[1]]["correct"]
                           and not row["judge"][VARIANTS[2]]["correct"] for row in good),
        "no_definitions_only": sum(not row["judge"][VARIANTS[0]]["correct"]
                                   and not row["judge"][VARIANTS[1]]["correct"]
                                   and row["judge"][VARIANTS[2]]["correct"] for row in good),
    }
    result["structure"] = {
        "raw_selected_sections": sum(row["structure"][VARIANTS[0]]["selected_sections"]
                                     for row in good),
        "inline_selected_sections": sum(row["structure"][VARIANTS[1]]["selected_sections"]
                                        for row in good),
        "dropped_definition_sections": sum(
            row["structure"][VARIANTS[1]]["dropped_definition_count"] for row in good),
        "inline_definition_cards": sum(
            row["structure"][VARIANTS[1]]["definition_card_count"] for row in good),
        "raw_context_chars": sum(row["structure"][VARIANTS[0]]["context_chars"]
                                 for row in good),
        "inline_context_chars": sum(row["structure"][VARIANTS[1]]["context_chars"]
                                    for row in good),
        "no_definitions_context_chars": sum(
            row["structure"][VARIANTS[2]]["context_chars"] for row in good),
    }
    return result


def _write_cases(blob: dict) -> dict:
    case_dir = ADR_DIR / "cases-inline-abc"
    case_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"files": []}
    for position, row in enumerate(blob["rows"], 1):
        path = case_dir / f"{position:03d}-{row['case_no']}.md"
        if row.get("error"):
            text = f"# {row['case_no']}\n\n오류: `{row['error']}`\n"
        else:
            parts = [f"# {row['case_no']} — 정의 표현 ABC\n", "## 질문\n",
                     row["question"], "\n## 사람 기준답변(채점 전용)\n",
                     row["reference_answer"], "\n## 구조 통계\n",
                     "```json\n" + json.dumps(row["structure"], ensure_ascii=False,
                                                indent=2) + "\n```\n"]
            for name in VARIANTS:
                parts.extend([
                    f"\n## {name} — 실제 제품 입력\n",
                    "### system\n", f"```text\n{row[name]['system_prompt']}\n```\n",
                    "### user\n", f"```text\n{row[name]['user_prompt']}\n```\n",
                    "### 제품 출력\n", row[name]["answer"], "\n",
                    f"- usage: `{json.dumps(row[name]['usage'], ensure_ascii=False)}`\n",
                    f"- wall_ms: {row[name]['wall_ms']}\n",
                ])
            parts.extend([
                "\n## Haiku ABC judge — 실제 입력\n",
                "### system\n", f"```text\n{row['judge_system_prompt']}\n```\n",
                "### user\n", f"```text\n{row['judge_user_prompt']}\n```\n",
                "### 출력\n", "```json\n" + json.dumps(row["judge_raw"],
                                                       ensure_ascii=False, indent=2)
                + "\n```\n", "### 정규화\n",
                "```json\n" + json.dumps(row["judge"], ensure_ascii=False, indent=2)
                + "\n```\n",
            ])
            text = "\n".join(parts)
        path.write_text(text, "utf-8")
        manifest["files"].append({
            "case_no": row["case_no"], "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    readme = case_dir / "README.md"
    readme.write_text("# ADR-0041 inline 정의 ABC 질문별 입출력\n\n" + "\n".join(
        f"- [{item['case_no']}]({Path(item['path']).name})"
        for item in manifest["files"]) + "\n", "utf-8")
    target = case_dir / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"directory": str(case_dir.relative_to(ROOT)), "files": len(manifest["files"]),
            "manifest": str(target.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", type=Path,
                        default=ROOT / "var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json")
    parser.add_argument("--answers", type=Path,
                        default=ROOT / "var/eval/e2e/cm_core_legalclosure_stage_answer_ab_51.json")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--cases", default="")
    parser.add_argument("--structure-only", action="store_true")
    args = parser.parse_args()

    stage = json.loads(args.stage.read_text("utf-8"))
    references = {row["case_no"]: row["reference_answer"]
                  for row in json.loads(args.answers.read_text("utf-8"))["rows"]}
    wanted = {item.strip() for item in args.cases.split(",") if item.strip()}
    sources = [row for row in stage["rows"] if not wanted or row["case_no"] in wanted]
    index = index_mod.current().scoped(None)

    prepared = []
    for source in sources:
        selected = source["variants"]["control_d_then_verifier"]["selected"]
        variants, structure = {}, {}
        for name in VARIANTS:
            variants[name], structure[name] = build_sections(index, selected, name)
        picks = _wiki_picks(source["question"], variants["no_definitions"])
        prepared.append({"source": source, "sections": variants,
                         "structure": structure, "picks": picks})
    if args.structure_only:
        public = []
        for row in prepared:
            public.append({"case_no": row["source"]["case_no"],
                           "question": row["source"]["question"],
                           "structure": row["structure"]})
        result = {"experiment": "ADR-0041-inline-definition-structure-only",
                  "llm_calls": 0, "rows": public}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(json.dumps({"cases": len(public),
                          "cards": sum(r["structure"][VARIANTS[1]]["definition_card_count"]
                                       for r in public)}, ensure_ascii=False, indent=1))
        return 0

    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU:
        raise SystemExit(f"모든 LLM은 {HAIKU}여야 합니다: {getattr(prototype, 'model', None)}")
    local = threading.local()

    def evaluate(prepared_row):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm is None or local.llm.model != HAIKU:
                raise RuntimeError("worker model is not Haiku")
        llm = local.llm
        source = prepared_row["source"]
        case_no, question = source["case_no"], source["question"]
        product_order, judge_order = _orders(case_no)
        generated = {}
        for name in product_order:
            user = _prompt(question, prepared_row["sections"][name], prepared_row["picks"])
            generated[name] = _generate(llm, name, answer.ANSWER_SYSTEM, user)
        labels = {name: chr(65 + pos) for pos, name in enumerate(judge_order)}
        judge_user = f"[기준답변]\n{references[case_no]}"
        for name in judge_order:
            judge_user += f"\n\n[답변 {labels[name]}]\n{generated[name]['answer']}"
        j0 = len(llm.log)
        judged = llm.structured("eval.adr0041.abc", JUDGE_SYSTEM, judge_user,
                                JUDGE_SCHEMA, max_tokens=2000,
                                effort="medium", model=HAIKU)
        judge_usage = _usage(list(llm.log)[j0:])
        if judged is None:
            raise RuntimeError("ABC judge failed")
        normalized = {name: {"correct": bool(judged[labels[name]]["correct"]),
                             "reason": str(judged[labels[name]]["reason"])[:800]}
                      for name in VARIANTS}
        return {"case_no": case_no, "question": question,
                "reference_answer": references[case_no],
                "structure": prepared_row["structure"],
                **generated, "product_order": list(product_order),
                "judge_order": labels, "judge_system_prompt": JUDGE_SYSTEM,
                "judge_user_prompt": judge_user, "judge_raw": judged,
                "judge": normalized, "judge_usage": judge_usage}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows, positions = [], {row["source"]["case_no"]: i for i, row in enumerate(prepared)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): row["source"]["case_no"] for row in prepared}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_no = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                source = next(x["source"] for x in prepared if x["source"]["case_no"] == case_no)
                row = {"case_no": case_no, "question": source["question"],
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda item: positions[item["case_no"]])
            partial = {"experiment": "ADR-0041-inline-same-doc-definition-abc",
                       "model_contract": {name: HAIKU for name in (*VARIANTS, "judge")},
                       "summary": _summary(rows), "rows": rows}
            args.out.write_text(json.dumps(partial, ensure_ascii=False, indent=1) + "\n",
                                "utf-8")
            marks = row.get("judge") or {}
            print(f"[{position:02d}/{len(prepared)}] {case_no} " + " ".join(
                f"{name[:2]}={'○' if (marks.get(name) or {}).get('correct') else '✗'}"
                for name in VARIANTS), flush=True)
    result = json.loads(args.out.read_text("utf-8"))
    result["case_markdown"] = _write_cases(result)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
