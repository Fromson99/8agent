#!/usr/bin/env python3
"""현재 운영 검색 경로를 골든·홀드아웃·블라인드 질문으로 직접 벤치마크한다.

답변 합성 품질이 아니라 ``vecfirst``의 근거 회수, 채널 사용, 후보량, 검색 지연을
잰다. 옛 Concept 골든의 음성은 Assertion/OQL 진입 차단용이므로 현재의 명시 조문
검색에는 정답/오답 게이트로 쓰지 않고 별도 진단값으로만 낸다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import yaml


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
DEFAULT_SUITES = [
    ROOT / "01_DATA" / "bench" / "concept_golden.yaml",
    ROOT / "01_DATA" / "bench" / "concept_holdout.yaml",
    ROOT / "01_DATA" / "bench" / "concept_blind.yaml",
]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    rows = sorted(values)
    pos = max(0, min(len(rows) - 1, math.ceil(len(rows) * pct) - 1))
    return round(float(rows[pos]), 3)


def _expected(case: dict) -> set[tuple[str, str]]:
    rows = case.get("expect_sources")
    if rows is None and case.get("expect_source"):
        rows = [case["expect_source"]]
    return {(str(row["doc_id"]), str(row["node"])) for row in (rows or [])}


def _usage(exchanges: list) -> dict:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((row.usage or {}).get("input_tokens", 0))
                            for row in exchanges),
        "output_tokens": sum(int((row.usage or {}).get("output_tokens", 0))
                             for row in exchanges),
        "duration_ms": sum(int(row.dur_ms) for row in exchanges),
        "errors": sum(bool(row.error) for row in exchanges),
    }


def _summary(rows: list[dict], *, index_load_ms: float) -> dict:
    positives = [row for row in rows if row["expect_hit"]]
    negatives = [row for row in rows if not row["expect_hit"]]
    latencies = [float(row["latency_ms"]) for row in rows]
    warm = latencies[1:] if len(latencies) > 1 else latencies
    expected_total = sum(len(row["expected_sources"]) for row in positives)
    expected_final = sum(int(row["expected_final_hits"]) for row in positives)
    expected_entry = sum(int(row["expected_entry_hits"]) for row in positives)
    final_total = sum(int(row["final_count"]) for row in positives)
    channel_totals: Counter[str] = Counter()
    strategies: Counter[str] = Counter()
    pruning: Counter[str] = Counter()
    for row in rows:
        channel_totals.update(row["channel_counts"])
        strategies[row["strategy"] or "none"] += 1
        pruning[row["pruning"] or "none"] += 1
    usage = {
        key: sum(int(row["usage"].get(key, 0)) for row in rows)
        for key in ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    }
    return {
        "cases": len(rows), "positive_cases": len(positives),
        "legacy_negative_cases": len(negatives),
        "positive_case_source_recall": round(
            sum(bool(row["expected_final_hits"]) for row in positives)
            / max(len(positives), 1), 6),
        "positive_coordinate_recall": round(expected_final / max(expected_total, 1), 6),
        "structured_entry_coordinate_recall": round(
            expected_entry / max(expected_total, 1), 6),
        "positive_expected_share_of_context": round(
            expected_final / max(final_total, 1), 6),
        # 옛 음성은 잘못된 술어/좌표에서 Concept OQL이 빈손이어야 한다는 계약이다.
        # 명시 좌표를 그대로 읽는 현재 RAG 품질 게이트로 해석하면 안 된다.
        "legacy_negative_structured_lock_rate": round(
            sum(bool(row["coordinate_locked"]) for row in negatives)
            / max(len(negatives), 1), 6),
        "definition_expansion_cases": sum(bool(row["definition_expansions"])
                                          for row in rows),
        "literal_fragment_cases": sum(bool(row["literal_fragments"]) for row in rows),
        "index_load_ms": round(index_load_ms, 3),
        "first_query_ms": round(latencies[0], 3) if latencies else 0.0,
        "latency_ms": {
            "mean": round(statistics.fmean(warm), 3) if warm else 0.0,
            "p50": _percentile(warm, 0.50), "p95": _percentile(warm, 0.95),
            "max": round(max(warm), 3) if warm else 0.0,
        },
        "final_contexts": {
            "mean": round(statistics.fmean(row["final_count"] for row in rows), 3),
            "p95": _percentile([row["final_count"] for row in rows], 0.95),
            "max": max((row["final_count"] for row in rows), default=0),
        },
        "strategies": dict(sorted(strategies.items())),
        "pruning": dict(sorted(pruning.items())),
        "channel_totals": dict(sorted(channel_totals.items())),
        "usage": usage,
    }


def main() -> int:
    os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "01_DATA" / "structure"))
    os.environ.setdefault("GLOSSARY_STORE", str(ROOT / "01_DATA" / "glossary.json"))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", action="append", type=Path,
                    help="YAML 시험판. 생략하면 golden/holdout/blind 3개")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--live-llm", action="store_true")
    guide_group = ap.add_mutually_exclusive_group()
    guide_group.add_argument("--query-guide", dest="query_guide", action="store_true",
                             help="DB 역매칭 해석 후보를 Span 분해기에 주입")
    guide_group.add_argument("--no-query-guide", dest="query_guide", action="store_false",
                             help="기존 질문 단독 Span 분해")
    ap.set_defaults(query_guide=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append",
                    help="지정한 case id만 실행(여러 번 사용 가능)")
    ap.add_argument("--positive-only", action="store_true")
    ap.add_argument("--negative-only", action="store_true")
    ap.add_argument("--scoped-only", action="store_true",
                    help="axes.scope=unscoped 문항 제외")
    ap.add_argument("--unscoped-only", action="store_true",
                    help="axes.scope=unscoped 문항만 실행")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.query_guide is not None:
        os.environ["RAG_QUERY_GUIDE"] = "1" if args.query_guide else "0"

    from lawrag.core.rag import controls, index as index_mod, vecfirst

    llm = None
    if args.live_llm:
        from lawrag.core import llm as llm_mod
        if not llm_mod.available():
            print(f"LLM 없음 — {llm_mod.MISSING_HINT}", file=sys.stderr)
            return 2
        llm = llm_mod.LLM()

    started = time.perf_counter()
    idx = index_mod.current()
    index_load_ms = (time.perf_counter() - started) * 1000
    rows = []
    suites = args.suite or DEFAULT_SUITES
    cases = []
    suite_meta = []
    for path in suites:
        spec = yaml.safe_load(path.read_text("utf-8")) or {}
        suite_meta.append({"path": str(path), "name": spec.get("name"),
                           "cases": len(spec.get("cases") or []),
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        cases.extend((path, spec, case) for case in (spec.get("cases") or []))
    if args.positive_only and args.negative_only:
        ap.error("--positive-only와 --negative-only는 함께 쓸 수 없습니다")
    if args.scoped_only and args.unscoped_only:
        ap.error("--scoped-only와 --unscoped-only는 함께 쓸 수 없습니다")
    if args.positive_only:
        cases = [row for row in cases if bool(row[2].get("expect_hit"))]
    if args.negative_only:
        cases = [row for row in cases if not bool(row[2].get("expect_hit"))]
    if args.scoped_only:
        cases = [row for row in cases
                 if str((row[2].get("axes") or {}).get("scope") or "") != "unscoped"]
    if args.unscoped_only:
        cases = [row for row in cases
                 if str((row[2].get("axes") or {}).get("scope") or "") == "unscoped"]
    if args.case_id:
        wanted = set(args.case_id)
        cases = [row for row in cases if str(row[2].get("id")) in wanted]
    if args.limit:
        cases = cases[:max(0, args.limit)]

    for pos, (path, spec, case) in enumerate(cases, 1):
        log0 = len(llm.log) if llm is not None else 0
        t0 = time.perf_counter()
        sections, meta = vecfirst.retrieve(
            idx, str(case["question"]), llm=llm, raw_query=str(case["question"]))
        latency_ms = (time.perf_counter() - t0) * 1000
        concept = meta.get("concept") or {}
        combination = meta.get("combination") or {}
        active = combination if meta.get("combination_hits") else concept
        expected = _expected(case)
        final = {(str(section.doc_id), str(section.node)) for section in sections}
        entry = {(str(row.get("doc_id")), str(row.get("node")))
                 for row in [*(meta.get("combination_hits") or []),
                             *(meta.get("concept_hits") or [])]}
        usage = _usage(list(llm.log)[log0:]) if llm is not None else _usage([])
        row = {
            "suite": str(spec.get("name") or path.stem), "id": str(case["id"]),
            "question": str(case["question"]), "expect_hit": bool(case["expect_hit"]),
            "axes": case.get("axes") or {},
            "expected_sources": sorted(expected),
            "expected_final_hits": len(expected & final),
            "expected_entry_hits": len(expected & entry),
            "entry_sources": sorted(entry), "final_sources": sorted(final),
            "final_count": len(sections), "latency_ms": round(latency_ms, 3),
            "strategy": str(active.get("strategy") or ""),
            "pruning": str(active.get("pruning") or ""),
            "fallback": str(active.get("fallback") or ""),
            "coordinate_locked": meta.get("entry_policy") in {
                "coordinate-intersection-only", "candidate-combinations-only"},
            "candidate_count": int(active.get("candidate_count")
                                   or active.get("option_count") or 0),
            "definition_expansions": concept.get("definition_expansions") or [],
            "literal_fragments": concept.get("literal_fragments") or [],
            "spans": active.get("spans") or [],
            "menus": concept.get("menus") or [],
            "landings": concept.get("landings") or [],
            "intersection": concept.get("intersection") or [],
            "query_guide": active.get("query_guide") or {"enabled": False},
            "combination_counts": combination.get("combination_counts") or {},
            "general_search": combination.get("general_search") or {},
            "channel_counts": {key: int(value) for key, value in (meta.get("counts") or {}).items()
                               if key in {"combination", "concept", "memory", "keyword", "frame",
                                          "vector", "floor", "doc_companion"}},
            "usage": usage,
        }
        rows.append(row)
        if args.verbose or pos % 10 == 0 or pos == len(cases):
            mark = "○" if (not row["expect_hit"] or row["expected_final_hits"]) else "✗"
            print(f"[{pos:>3}/{len(cases)}] {mark} {row['id']} "
                  f"ctx={row['final_count']} {row['latency_ms']:.0f}ms "
                  f"route={row['strategy'] or row['fallback'] or 'fallback'}")

    control_rows = controls.snapshot()
    report = {
        "schema_version": 1, "kind": "rag_search_benchmark",
        "live_llm": bool(llm), "suites": suite_meta,
        "variant": {"query_guide": os.environ.get("RAG_QUERY_GUIDE", "default")},
        "controls": {"fingerprint": controls.fingerprint(control_rows),
                     "values": control_rows},
        "summary": _summary(rows, index_load_ms=index_load_ms), "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
