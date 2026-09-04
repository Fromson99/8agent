#!/usr/bin/env python3
"""실제 질의응답 회수·합성 경로를 끝까지 재는 법률 E2E 골든.

``review_golden.py``는 사실→요건→포섭 전용 검토 엔진의 골든이다. 이 러너는
운영 ``/ask mode=vector``의 핵심 경로를 그대로 사용해 Concept·승인 키워드·
문서 동반 같은 공용 RAG 스위치의 한 변수 A/B를 실제로 잰다. 진단 원장 쓰기와
사후 감사만 생략한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 환경 기본값을 먼저 세운다


DIRECTION_SYSTEM = (
    "너는 법률 답변이 최종적으로 확정한 법률 명제의 극성을 판정한다. 첫 '예/아니요'나 "
    "질문의 부정형은 버리고, 의무·권리·허용·책임·해당 여부를 이중부정까지 풀어 본다. "
    "'아니요, 하여야 한다', '알리지 않을 수 없다', '없다는 주장은 잘못이다'는 긍정이다. "
    "'예, 할 필요가 없다', '해당하지 않는다', '할 수 없다'는 부정이다. 사정에 따라 "
    "현재 질문의 결론이 실제로 갈리거나 유보될 때만 조건부다. 질문 사실에는 원칙 결론을 "
    "확정한 뒤 일반적인 법정 예외·단서를 덧붙인 답은 그 원칙 결론의 극성이다. 답이 없거나 "
    "결론을 전혀 내리지 못하면 미정이다. 설명 없이 enum 하나만 구조화해 낸다."
)
DIRECTION_SCHEMA = {
    "type": "object",
    "properties": {"direction": {"type": "string",
                                  "enum": ["긍정", "부정", "조건부", "미정"]}},
    "required": ["direction"], "additionalProperties": False,
}
EVAL_MODEL = "claude-sonnet-5"
SEMANTIC_SYSTEM = (
    "너는 법률 E2E 답변 채점자다. [기준답변]은 현업 원문에서 사람이 확정한 "
    "정답이다. [시스템 답변]이 그 답의 결론을 명확히 지지하고 모순하지 않으면 correct=true다. "
    "질문의 부정형 표현이나 첫 '예/아니오'가 아니라 답변 전체의 법률 내용을 본다. "
    "논리적 이중부정을 반드시 정규화한다. 예: '제척하지 않으면 안 된다'는 '제척해야 "
    "한다'와 같고, '알리지 않아도 되나요? 아니오'는 '알려야 한다'와 같다. 기대 명제를 "
    "지지한 뒤 관련된 추가 의무·예외를 설명해도 기준답변과 모순하지 않으면 정답이다. "
    "기준답변이 수치·기간·계산식·요건·예외를 직접 묻는다면 그 핵심 세부사항까지 맞아야 "
    "materially_complete=true다. 결론이 맞아도 질문이 요구한 핵심 세부사항을 빠뜨리면 "
    "correct=false다. 더 정확한 조건·예외를 설명하는 것은 정답이다. 근거가 없다고 회피하거나 "
    "반대로 말하거나 다른 규범만 답하거나 중요한 수치·기간을 틀리면 false다."
)
SEMANTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "conclusion_correct": {"type": "boolean"},
        "materially_complete": {"type": "boolean"},
        "no_material_error": {"type": "boolean"},
        "reason": {"type": "string"},
        "missing_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["correct", "reason"], "additionalProperties": False,
}


_ARTICLE = re.compile(r"(제\d+(?:-\d+)?조(?:의\d+)?)")


def _mix_modes(idx, cases: list[dict], mix: str) -> dict[str, str]:
    a_pct = int(mix.split(":")[0])
    picked = [c for c in cases if (c.get("answer") or "")
              and review.material_status(idx, c)[0] == "전부"]
    picked.sort(key=lambda c: c["case_no"])
    n_a = round(len(picked) * a_pct / 100)
    a_ok = [c for c in picked if review.question_mode(idx, c.get("issue") or "") == "A"]
    step = max(len(a_ok) // max(n_a, 1), 1)
    a_set = {c["case_no"] for c in a_ok[::step][:n_a]}
    return {c["case_no"]: ("A" if c["case_no"] in a_set else "B") for c in picked}


def _question(llm, case: dict, mode: str) -> tuple[str, str]:
    if mode == "A":
        return (case.get("issue") or "")[:2000], "질의요지"
    fresh = (review.marked().get(case["case_no"]) or {}).get("colloquial")
    return (fresh or review.colloquial_of(llm, case))[:2000], "구어"


def _coords(rows) -> set[tuple[str, str]]:
    from lawrag.core.rag import wikictx

    out = set()
    for row in rows:
        doc = row.get("doc") if isinstance(row, dict) else row.doc
        path = row.get("path") if isinstance(row, dict) else row.path
        prefix = "부칙 " if "부칙" in (path or "") else ""
        for jo in _ARTICLE.findall(path or ""):
            out.add((wikictx._pack(doc or ""), prefix + jo))
    return out


def _expected_article_coords(case: dict) -> set[tuple[str, str]]:
    """현업 골든의 법령·조 좌표를 검색/인용 path와 같은 모양으로 만든다."""
    from lawrag.core.rag import wikictx

    return {
        (wikictx._pack(str(row.get("law") or "")),
         str(row.get("article") or ""))
        for row in case.get("expected_articles") or []
        if row.get("law") and row.get("article")
    }


def _current_material(idx, expected: set[tuple[str, str]]) -> tuple[str, int]:
    """현재 코퍼스에 정답 조문이 실제로 있는지 실행 시점에 다시 잰다."""
    from lawrag.core.rag import wikictx

    by_law = {wikictx._pack(view.name): view for view in idx.docs.values()}
    have = 0
    for law, article in expected:
        view = by_law.get(law)
        if view is None:
            continue
        found = False
        for node_id in view.by_id:
            path = view.path(node_id) or ""
            if "부칙" in path:
                continue
            if any(segment == article or segment.startswith(article + " ")
                   for segment in path.split(" ▸ ")):
                found = True
                break
        have += int(found)
    material = ("complete" if have == len(expected) else
                "missing" if have == 0 else "partial")
    return material, have


def _reference_answer(case: dict) -> str:
    return str(case.get("reference_answer") or case.get("expected_claim") or "")


def _semantic_grade(llm, case: dict, system_answer: str) -> tuple[dict, dict]:
    reference = _reference_answer(case)
    start = len(llm.log)
    grade = llm.structured(
        "eval.answer.semantic", SEMANTIC_SYSTEM,
        f"[질문]\n{case['question']}\n\n[기준답변]\n{reference}\n\n"
        f"[시스템 답변]\n{system_answer[:8000]}\n\n"
        "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.",
        SEMANTIC_SCHEMA, max_tokens=1600, effort="medium", model=EVAL_MODEL)
    return dict(grade or {}), _usage(list(llm.log)[start:])


def _usage(exchanges: list) -> dict:
    truncated = [x for x in exchanges
                 if getattr(x, "stop_reason", "") == "max_tokens"
                 or ("max_tokens" in str(getattr(x, "error", ""))
                     and "잘림" in str(getattr(x, "error", "")))]
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((x.usage or {}).get("input_tokens", 0)) for x in exchanges),
        "output_tokens": sum(int((x.usage or {}).get("output_tokens", 0)) for x in exchanges),
        "duration_ms": sum(int(x.dur_ms) for x in exchanges),
        "ttft_ms": max((int(x.ttft_ms) for x in exchanges), default=0),
        "errors": sum(bool(x.error) for x in exchanges),
        "truncated_calls": len(truncated),
        "truncation_stages": [str(x.kind) for x in truncated],
    }


def _ask_core(llm, idx, question: str) -> dict:
    from lawrag.core.rag import answer as answer_mod
    from lawrag.core.rag import promote, switches, vecfirst, wikictx

    t0 = time.perf_counter()
    log0 = len(llm.log)
    spots = wikictx.spot(question) if switches.is_on("issue_spot") else []
    if switches.is_on("issue_spot_pre"):
        judged = wikictx.spot_llm(llm, question, index=idx)
        if judged is not None:
            spots = judged
    qx = wikictx.expand_query(question, spots) if spots else question
    qv = wikictx.vector_query(question, spots) if spots else ""
    memory = promote.direct_hits(question)
    sections, meta = vecfirst.retrieve(idx, qx, llm=llm, vec_query=qv,
                                       seeds=memory, raw_query=question)
    sections, scope_meta = answer_mod.enforce_scope(idx, sections)
    answer_mod.repair_landings(llm, idx, sections)
    ans = answer_mod.synthesize(llm, question, sections, spots=spots)
    product_exchanges = list(llm.log)[log0:]
    product_sec = round(time.perf_counter() - t0, 1)

    if not ans.answer or not ans.answerable:
        direction = "미정"
        eval_usage = {}
    else:
        e0 = len(llm.log)
        grade = llm.structured(
            "eval.answer.direction", DIRECTION_SYSTEM,
            f"[답변]\n{ans.answer[:6000]}",
            DIRECTION_SCHEMA, max_tokens=300, effort="medium", model=EVAL_MODEL)
        direction = str((grade or {}).get("direction") or "미정")
        eval_usage = _usage(list(llm.log)[e0:])

    usage = _usage(product_exchanges)
    counts = dict(meta.get("counts") or {})
    truncation_stages = list(usage.pop("truncation_stages"))
    return {
        "sections": sections, "answer": ans, "direction": direction,
        "spots": spots, "usage": usage, "evaluation_usage": eval_usage, "meta": meta,
        "counts": counts, "truncation_stages": truncation_stages,
        "scope_meta": scope_meta, "sec": product_sec,
    }


def _runtime(core: dict) -> dict:
    sections, usage, counts = core["sections"], core["usage"], core["counts"]
    meta = core.get("meta") or {}
    concept_meta = meta.get("concept") or {}
    combination_meta = meta.get("combination") or {}
    return {
        "final_contexts": len(sections),
        "context_chars": sum(len(s.text or "") for s in sections),
        "truncated_sections": int(usage.get("truncated_calls", 0)),
        "truncation_stages": core["truncation_stages"],
        "shared_cap_overflow": bool(counts.get("over_shared_cap")),
        "channel_counts": {k: int(v) for k, v in counts.items()
                           if k in {"combination", "concept", "memory", "keyword", "frame", "vector",
                                    "floor", "doc_companion"}},
        "stage_counts": {
            "issue_spot": len(core.get("spots") or []),
            "retrieval": len(sections),
            "answer_synthesis": int(bool(core["answer"].answer)),
            "final_citation": len(core["answer"].refs),
        },
        "channel_details": {
            "combination": [{"doc_id": str(r.get("doc_id")), "node": str(r.get("node"))}
                            for r in meta.get("combination_hits") or []],
            "concept": [{"doc_id": str(r.get("doc_id")), "node": str(r.get("node"))}
                        for r in meta.get("concept_hits") or []],
            "keyword": [{"doc_id": str(r.get("doc_id")), "node": str(r.get("node"))}
                        for r in meta.get("keywords") or []],
            "doc_companion": [{"doc_id": str(r.get("doc_id")), "node": str(r.get("node"))}
                               for r in meta.get("doc_companion") or []],
        },
        "scope_dropped": len(core["scope_meta"].get("dropped") or []),
        "query_guide": (combination_meta.get("query_guide")
                        or concept_meta.get("query_guide")
                        or {"enabled": False}),
        "combination": {
            "strategy": combination_meta.get("strategy") or "",
            "fallback": combination_meta.get("fallback") or "",
            "spans": combination_meta.get("spans") or [],
            "structure": combination_meta.get("structure") or {},
            "groups": combination_meta.get("groups") or [],
            "expansion_order": combination_meta.get("expansion_order") or [],
            "tree_counts": combination_meta.get("tree_counts") or {},
            "counts": combination_meta.get("combination_counts") or {},
            "coordinate_option_count": int(
                combination_meta.get("coordinate_option_count") or 0),
            "option_count": int(combination_meta.get("option_count") or 0),
            "general_keywords": (combination_meta.get("general_search") or {}).get(
                "keywords") or [],
            "choice": combination_meta.get("choice") or {},
            "selected": combination_meta.get("selected") or [],
            "exploration": combination_meta.get("exploration") or {},
        },
    }


def run_one(llm, idx, case: dict, question: str, mode: str, text_kind: str) -> dict:
    core = _ask_core(llm, idx, question)
    sections, ans = core["sections"], core["answer"]
    retrieved = _coords(sections)
    cited = _coords(ans.refs)
    want = {(law, jo) for law, jo in review.want_articles(case)}
    from lawrag.core.rag import wikictx
    want = {(wikictx._pack(law), jo) for law, jo in want}
    got_docs = {s.doc for s in sections}
    want_laws = set(case.get("laws") or [])
    material, material_n, material_have = review.material_status(idx, case)
    return {
        "case_no": case["case_no"], "label": (case.get("label") or "")[:60],
        "mode": mode, "text_kind": text_kind, "material": material,
        "material_have": f"{material_have}/{material_n}",
        "basis_hit": len(want & cited), "basis_n": len(cited),
        "basis_stray": len(cited - want) if want else 0,
        "basis_raw": [f"{r.get('doc')} {r.get('path')}" for r in ans.refs][:12],
        "want_arts_list": sorted(f"{law} {jo}" for law, jo in review.want_articles(case)),
        "issues": len(core["spots"]), "by_net": 0, "norms": len(sections), "subs": 0,
        "unclear": 0 if ans.answerable else 1, "direction": core["direction"],
        "interp": bool(ans.answerable), "answer": ans.answer[:2000],
        "want_laws": sorted(want_laws), "got_laws": sorted(got_docs & want_laws),
        "want_arts": len(want), "got_arts": len(want & retrieved),
        "sec": core["sec"], "usage": core["usage"],
        "evaluation_usage": core["evaluation_usage"], "runtime": _runtime(core),
    }


def _direct_question(case: dict, form: str = "standalone") -> str:
    """현업 골든의 실제 단일턴 입력. raw는 문맥 보완 효과를 재는 ablation이다."""
    if form == "raw":
        return str(case.get("source_question") or case["question"])
    return str(case["question"])


def run_direct_one(llm, idx, case: dict, question_form: str = "standalone") -> dict:
    evaluated_question = _direct_question(case, question_form)
    core = _ask_core(llm, idx, evaluated_question)
    sections, ans = core["sections"], core["answer"]
    expected_nodes = {(str(r["doc_id"]), str(r["node"]))
                      for r in case.get("expect_sources") or []}
    expected_articles = _expected_article_coords(case)
    expected = expected_articles or expected_nodes
    n = len(expected)
    if expected_articles:
        retrieved = _coords(sections)
        cited = _coords(ans.refs)
        expected_display = sorted(f"{law} {article}"
                                  for law, article in expected_articles)
        material, material_have = _current_material(idx, expected_articles)
    else:
        retrieved = {(str(s.doc_id), str(s.node)) for s in sections}
        cited = {(str(r.get("doc_id")), str(r.get("node"))) for r in ans.refs}
        expected_display = [f"{d} node={node}" for d, node in sorted(expected_nodes)]
        material, material_have = str(case.get("material") or "정본"), n
    semantic, semantic_usage = _semantic_grade(llm, case, ans.answer)
    reference_answer = _reference_answer(case)
    return {
        "case_no": str(case["id"]), "label": str(case["question"])[:60],
        "question": evaluated_question,
        "source_question": str(case.get("source_question") or case["question"]),
        "reference_answer": reference_answer,
        "reference_answer_kind": str(case.get("reference_answer_kind") or "golden"),
        "mode": str(case.get("mode") or "B"),
        "text_kind": f"직접질문:{question_form}",
        "material": material, "material_have": f"{material_have}/{n}",
        "m_n": n, "m_ret": len(expected & retrieved),
        "m_basis": len(expected & cited), "m_gold": str(case.get("direction") or ""),
        "basis_hit": len(expected & cited), "basis_n": len(cited),
        "basis_stray": len(cited - expected),
        "basis_raw": [f"{r.get('doc')} {r.get('path')}" for r in ans.refs][:12],
        "want_arts_list": expected_display,
        "issues": len(core["spots"]), "by_net": 0, "norms": len(sections), "subs": 0,
        "unclear": 0 if ans.answerable else 1, "direction": core["direction"],
        "interp": bool(ans.answerable), "answer": ans.answer,
        "semantic_correct": bool((semantic or {}).get("correct")),
        "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
        "semantic_grade": semantic,
        "semantic_usage": semantic_usage,
        "expected_articles": list(case.get("expected_articles") or []),
        "axes": {**dict(case.get("axes") or {}), "material": material},
        "want_laws": [], "got_laws": [], "want_arts": n,
        "got_arts": len(expected & retrieved), "sec": core["sec"],
        "usage": core["usage"], "evaluation_usage": core["evaluation_usage"],
        "runtime": _runtime(core),
    }


def regrade(llm, suite: dict, source: Path, out: Path, *, errors_only: bool = False) -> int:
    blob = json.loads(source.read_text(encoding="utf-8"))
    expected = {str(c["id"]): c for c in suite.get("cases") or []}
    rows = list(blob.get("rows") or [])
    regraded = 0
    for i, row in enumerate(rows, 1):
        case = expected.get(str(row.get("case_no")))
        semantic_usage = dict(row.get("semantic_usage") or {})
        if errors_only and not (semantic_usage.get("errors")
                                or semantic_usage.get("truncated_calls")):
            continue
        start = len(llm.log)
        if not errors_only:
            direction = llm.structured(
                "eval.answer.direction", DIRECTION_SYSTEM,
                f"[시스템 답변]\n{str(row.get('answer') or '')[:6000]}",
                DIRECTION_SCHEMA, max_tokens=300, effort="medium", model=EVAL_MODEL)
            row["direction"] = str((direction or {}).get("direction") or "미정")
        if case is not None:
            semantic, semantic_usage = _semantic_grade(
                llm, case, str(row.get("answer") or ""))
            row["semantic_correct"] = bool((semantic or {}).get("correct"))
            row["semantic_reason"] = str((semantic or {}).get("reason") or "")[:500]
            row["semantic_grade"] = semantic
            row["semantic_usage"] = semantic_usage
            row["question"] = str(row.get("question") or case["question"])
            row["source_question"] = str(case.get("source_question") or case["question"])
            row["reference_answer"] = _reference_answer(case)
        row["evaluation_usage"] = _usage(list(llm.log)[start:])
        regraded += 1
        print(f"  [{i}/{len(rows)}] {row['direction']} {row.get('case_no')}"
              + (f" · 의미 {'○' if row.get('semantic_correct') else '✗'}"
                 if case is not None else ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    requirements = _flow_requirements(suite)
    coverage = _coverage(rows, requirements.get("required_channels")
                         or suite.get("required_channels") or [])
    out.write_text(json.dumps({**blob, "flow": "ask", "suite": suite, "rows": rows,
                               "channel_coverage": coverage},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if expected:
        print(f"의미 재채점 {sum(bool(r.get('semantic_correct')) for r in rows)}/{len(rows)}"
              f" · 갱신 {regraded}건")
    return 0


def _coverage(rows: list[dict], required: list[str]) -> dict:
    totals: dict[str, int] = {}
    for row in rows:
        counts = (row.get("runtime") or {}).get("channel_counts") or {}
        for channel, count in counts.items():
            totals[str(channel)] = totals.get(str(channel), 0) + int(count)
    wanted = list(dict.fromkeys(str(channel) for channel in required))
    observed = [channel for channel in wanted if totals.get(channel, 0) > 0]
    return {
        "required": wanted,
        "observed": observed,
        "missing": [channel for channel in wanted if channel not in observed],
        "rate": round(len(observed) / len(wanted), 6) if wanted else 1.0,
        "totals": dict(sorted(totals.items())),
    }


def _flow_requirements(suite: dict) -> dict:
    return dict((suite.get("flows") or {}).get("ask") or {})


def main() -> int:
    from lawrag.core.rag import controls, evaluation
    from lawrag.core.rag import index as index_mod

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--regrade", type=Path,
                    help="저장된 direct E2E 답변을 운영 재실행 없이 의미만 다시 채점")
    ap.add_argument("--regrade-errors-only", action="store_true",
                    help="--regrade에서 평가 오류·잘림 행만 다시 채점")
    ap.add_argument("--question-form", choices=("standalone", "raw"),
                    default="standalone",
                    help="직접질문 골든 입력: 문맥을 포함한 단일턴 또는 원문 ablation")
    ap.add_argument("--case-id", action="append", default=[],
                    help="실행할 direct case ID. 반복 지정하거나 쉼표로 묶을 수 있음")
    guide_group = ap.add_mutually_exclusive_group()
    guide_group.add_argument("--query-guide", dest="query_guide", action="store_true")
    guide_group.add_argument("--no-query-guide", dest="query_guide", action="store_false")
    ap.set_defaults(query_guide=None)
    args = ap.parse_args()
    if args.query_guide is not None:
        os.environ["RAG_QUERY_GUIDE"] = "1" if args.query_guide else "0"
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    direct_cases = list(suite.get("cases") or [])
    requested_ids = list(dict.fromkeys(
        case_id.strip()
        for value in args.case_id
        for case_id in value.split(",")
        if case_id.strip()
    ))
    if requested_ids:
        available_ids = {str(case.get("id")) for case in direct_cases}
        missing_ids = [case_id for case_id in requested_ids
                       if case_id not in available_ids]
        if missing_ids:
            print("없는 direct case: " + " · ".join(missing_ids), file=sys.stderr)
            return 2
        wanted_ids = set(requested_ids)
        direct_cases = [case for case in direct_cases
                        if str(case.get("id")) in wanted_ids]
    wanted = [str(x) for x in suite.get("case_nos") or []]
    mix = str(suite.get("mix") or "20:80")
    labels = json.loads(review.LABELS.read_text("utf-8"))
    cases = review._cases()
    by_no = {c["case_no"]: c for c in cases}
    missing = [x for x in wanted if x not in by_no]
    if missing:
        print("없는 사건: " + " · ".join(missing), file=sys.stderr)
        return 2
    llm = review._llm()
    if llm is None:
        print("LLM 없음", file=sys.stderr)
        return 2
    if args.regrade:
        return regrade(llm, suite, args.regrade, args.out,
                       errors_only=args.regrade_errors_only)
    idx = index_mod.current()
    modes = _mix_modes(idx, cases, mix) if wanted else {}
    rows = []
    total = len(direct_cases) if direct_cases else len(wanted)
    print(f"운영 ask E2E {total}건 · {suite.get('name')}"
          + (f" · mix {mix}" if wanted else " · 직접질문"))
    iterable = direct_cases if direct_cases else wanted
    for i, item in enumerate(iterable, 1):
        if direct_cases:
            case_no = str(item["id"])
            try:
                row = run_direct_one(llm, idx, item, args.question_form)
            except Exception as exc:
                print(f"  !! {case_no} 실패: {type(exc).__name__}: {exc}")
                continue
            if item.get("direction"):
                labels[case_no] = str(item["direction"])
            mode = str(item.get("mode") or "B")
        else:
            case_no = str(item)
            case = by_no[case_no]
            mode = modes[case_no]
            question, text_kind = _question(llm, case, mode)
            try:
                row = run_one(llm, idx, case, question, mode, text_kind)
            except Exception as exc:
                print(f"  !! {case_no} 실패: {type(exc).__name__}: {exc}")
                continue
        rows.append(row)
        if direct_cases:
            mark = "○" if row.get("semantic_correct") else "✗"
        else:
            mark = {"적중": "○", "유보": "△", "오답": "✗", "미라벨": "·"}[
                review.verdict(labels.get(case_no), row["direction"])]
        if direct_cases:
            print(f"  [{i}/{total}] {mark} {case_no} {mode} "
                  f"ctx{row['norms']} cite{row['basis_n']} → "
                  f"의미 {'정답' if row.get('semantic_correct') else '오답'} "
                  f"{row['sec']}s")
        else:
            print(f"  [{i}/{total}] {mark} {case_no} {mode} "
                  f"ctx{row['norms']} cite{row['basis_n']} → {row['direction']} "
                  f"(정답 {labels.get(case_no)}) {row['sec']}s")
    control_rows = controls.snapshot()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    requirements = _flow_requirements(suite)
    channel_coverage = _coverage(
        rows, requirements.get("required_channels")
        or suite.get("required_channels") or [])
    args.out.write_text(json.dumps({
        "flow": "ask", "suite": suite, "rows": rows,
        "channel_coverage": channel_coverage,
        "controls": {"fingerprint": controls.fingerprint(control_rows),
                     "values": control_rows, "audit": controls.audit(control_rows)},
        "engine": evaluation.engine_snapshot(),
        "variant": {"query_guide": os.environ.get("RAG_QUERY_GUIDE", "default"),
                    "question_form": args.question_form,
                    "case_ids": requested_ids or "all"},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if not direct_cases:
        review.score(rows, labels)
    print(f"  필수 채널 {len(channel_coverage['observed'])}/"
          f"{len(channel_coverage['required'])} 관측"
          + (" · 미관측 " + ", ".join(channel_coverage["missing"])
             if channel_coverage["missing"] else ""))
    if direct_cases:
        semantic_hit = sum(bool(r.get("semantic_correct")) for r in rows)
        concept_cases = sum(int((r.get("runtime") or {}).get("channel_counts", {}).get("concept", 0)) > 0
                            for r in rows)
        combo_cases = sum(int((r.get("runtime") or {}).get("channel_counts", {}).get("combination", 0)) > 0
                          for r in rows)
        print(f"  의미 정답 {semantic_hit}/{len(rows)} · 조합 진입 {combo_cases}/{len(rows)}"
              f" · Concept 직접 진입 {concept_cases}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
