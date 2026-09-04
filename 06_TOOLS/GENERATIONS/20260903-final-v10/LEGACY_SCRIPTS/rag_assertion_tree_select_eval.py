#!/usr/bin/env python3
"""51개 골든에서 Assertion-first 트리의 소형 LLM 가지 선택만 평가한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 데이터 경로 환경 설정
from lawrag.core.rag import assertionfirst, conceptfirst  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402


def _usage(exchanges) -> dict:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((row.usage or {}).get("input_tokens", 0))
                            for row in exchanges),
        "output_tokens": sum(int((row.usage or {}).get("output_tokens", 0))
                             for row in exchanges),
        "duration_ms": sum(int(row.dur_ms) for row in exchanges),
        "errors": sum(bool(row.error) for row in exchanges),
    }


def _summary(rows: list[dict]) -> dict:
    gold = sum(len(row["gold"]) for row in rows)
    hits = sum(item["selected"] for row in rows for item in row["gold"])
    return {
        "cases": len(rows), "gold": gold, "selected_hits": hits,
        "selected_recall": round(hits / gold, 4) if gold else 0,
        "case_hits": sum(any(item["selected"] for item in row["gold"])
                         for row in rows),
        "calls": sum(row["usage"]["calls"] for row in rows),
        "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
        "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
        "duration_ms": sum(row["usage"]["duration_ms"] for row in rows),
        "errors": sum(row["usage"]["errors"] for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=51)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--page-size", type=int, choices=(8, 16, 32), default=32)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--cap", type=int, default=4)
    parser.add_argument("--model", default="",
                        help="비우면 환경 기본 모델, 지정하면 모든 선택 호출에 고정")
    parser.add_argument("--case-no", action="append", default=[],
                        help="지정한 case_no만 평가한다. 여러 번 지정 가능")
    args = parser.parse_args()

    source = json.loads(args.run.read_text(encoding="utf-8"))
    all_cases = list(source.get("rows") or [])[:51]
    if args.case_no:
        wanted = set(args.case_no)
        cases = [case for case in all_cases if case.get("case_no") in wanted]
        missing = wanted.difference(case.get("case_no") for case in cases)
        if missing:
            raise SystemExit(f"없는 case_no: {', '.join(sorted(missing))}")
    else:
        cases = all_cases[:max(0, args.limit)]
    old = json.loads(args.out.read_text(encoding="utf-8")) \
        if args.resume and args.out.is_file() else {"rows": []}
    rows = list(old.get("rows") or [])
    completed = {row["case_no"] for row in rows}
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    registry = conceptfirst.load_registry()
    assertionfirst.NAVIGATION_PAGE_SIZE = args.page_size
    assertionfirst.current(registry)  # 공유 읽기 전용 색인을 병렬 실행 전에 완성
    local = threading.local()

    class FixedModel:
        def __init__(self, inner, model):
            self.inner, self.model = inner, model

        @property
        def log(self):
            return self.inner.log

        def structured(self, *values, **kwargs):
            kwargs["model"] = self.model
            return self.inner.structured(*values, **kwargs)

    def evaluate(case):
        if not hasattr(local, "llm"):
            inner = review._llm()
            local.llm = FixedModel(inner, args.model) if args.model else inner
        llm = local.llm
        start_log = len(llm.log)
        started = time.perf_counter()
        sections, meta = assertionfirst.retrieve(
            index, str(case.get("question") or ""), registry, llm=llm,
            cap=args.cap)
        selected = _coords(sections)
        expected = _expected_article_coords(case)
        gold_rows = [{"law": law, "article": article,
                      "selected": (law, article) in selected}
                     for law, article in sorted(expected)]
        usage = _usage(llm.log[start_log:])
        return {
            "case_no": case.get("case_no"), "question": case.get("question"),
            "gold": gold_rows, "selected": meta.get("selected") or [],
            "tree": meta.get("tree") or {}, "structure": meta.get("structure") or {},
            "candidate_ranges": meta.get("candidate_ranges", 0),
            "fallback": meta.get("fallback") or "", "usage": usage,
            "wall_ms": round((time.perf_counter() - started) * 1000),
        }

    pending = [case for case in cases if case.get("case_no") not in completed]
    order = {case.get("case_no"): pos for pos, case in enumerate(cases)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_cases = {pool.submit(evaluate, case): case for case in pending}
        for done_no, future in enumerate(concurrent.futures.as_completed(future_cases), 1):
            row = future.result()
            rows.append(row)
            rows.sort(key=lambda item: order.get(item["case_no"], 10 ** 9))
            result = {
                "experiment": "assertion-first-small-llm-tree-selection-v1",
                "source": str(args.run), "model": args.model or prototype.model,
                "cap": args.cap,
                "navigation_page_size": args.page_size, "workers": args.workers,
                "summary": _summary(rows), "rows": rows,
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            hit_count = sum(item["selected"] for item in row["gold"])
            print(f"[{done_no:02d}/{len(pending)}] {row['case_no']} "
                  f"selected={hit_count}/{len(row['gold'])} "
                  f"calls={row['usage']['calls']} ranges={row['candidate_ranges']} "
                  f"wall={row['wall_ms']}ms", flush=True)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
