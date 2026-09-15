#!/usr/bin/env python3
"""Concept 진입 부품검사 — 정렬·근거·기존 질문 오염을 LLM 없이 잰다.

    .venv/bin/python scripts/concept_golden.py
    .venv/bin/python scripts/concept_golden.py --file data/bench/concept_golden.yaml

두 자를 함께 낸다.

1. 진입 부품검사: 표현 변형은 승인 Assertion 근거에 닿고 대조 질문은 폴백하는가.
2. 기존 골든 source-shadow: 기존 법령해석 질문 207개의 정답 evidence에서 실제
   법령·조·항·호 좌표를 해소해 Concept 진입이 그 밖의 근거를 끼워 넣지 않는가.
   이 검사는 답 생성이나 LLM을 부르지 않는다.

``--live-llm``은 50문항 중 ``live_llm: true``인 소수 canary만 실제 Span→부품
조립으로 검사한다. ``--case``를 함께 주면 지정 문항을 강제로 실행한다. 비용 폭주를
막기 위해 207문항 shadow는 자동 생략한다.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
import sys
from pathlib import Path

import yaml


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
DEFAULT = ROOT / "01_DATA" / "bench" / "concept_golden.yaml"
LEGACY = ROOT / "01_DATA" / "review" / "golden_labels_v2.json"


def _expected_sources(case: dict) -> set[tuple[str, str]]:
    rows = case.get("expect_sources")
    if rows is None and case.get("expect_source"):
        rows = [case["expect_source"]]
    return {(str(row["doc_id"]), str(row["node"])) for row in (rows or [])}


def _check(case: dict, sections: list, meta: dict, *, live_llm: bool = False) -> list[str]:
    errors = []
    expect_hit = bool(case.get("expect_hit"))
    if bool(sections) != expect_hit:
        errors.append(f"hit={bool(sections)} (expected {expect_hit})")
    pattern_key = "expect_llm_pattern" if live_llm else "expect_pattern"
    if case.get(pattern_key):
        got = (meta.get("oql") or {}).get("pattern")
        if got != case[pattern_key]:
            errors.append(f"pattern={got!r}")
    if case.get("expect_concepts"):
        got = {c["label"] for c in (meta.get("alignment") or {}).get("selected", [])}
        want = set(case["expect_concepts"])
        if (not live_llm and got != want) or (live_llm and not want <= got):
            errors.append(f"concepts={sorted(got)!r}")
    expected_sources = _expected_sources(case)
    if expected_sources:
        got = {(s.doc_id, str(s.node)) for s in sections}
        if got != expected_sources:
            errors.append(f"source={sorted(got)!r}")
    fallback_key = "expect_llm_fallback" if live_llm else "expect_fallback"
    expected_fallback = case.get(fallback_key)
    if expected_fallback:
        values = ([expected_fallback] if isinstance(expected_fallback, str)
                  else list(expected_fallback))
        got = str(meta.get("fallback") or "")
        if not any(str(value) in got for value in values):
            errors.append(f"fallback={got!r}")
    return errors


def _validate_spec(spec: dict) -> list[str]:
    """50문항과 분석 축이 조용히 흐트러지지 않게 CI 앞에서 검증한다."""
    errors = []
    cases = spec.get("cases")
    if not isinstance(cases, list):
        return ["cases는 목록이어야 함"]
    expected_count = spec.get("expected_count")
    if expected_count is not None and len(cases) != int(expected_count):
        errors.append(f"문항 수={len(cases)} (expected {expected_count})")
    axis_order = spec.get("axis_order") or []
    if not isinstance(axis_order, list) or not axis_order:
        errors.append("axis_order가 비어 있음")
        axis_order = []
    ids = []
    for pos, case in enumerate(cases, 1):
        prefix = f"cases[{pos}]"
        cid = str(case.get("id") or "").strip()
        if not cid:
            errors.append(f"{prefix}: id 없음")
        ids.append(cid)
        if not str(case.get("question") or "").strip():
            errors.append(f"{prefix}: question 없음")
        if not isinstance(case.get("expect_hit"), bool):
            errors.append(f"{prefix}: expect_hit은 bool이어야 함")
        axes = case.get("axes")
        if not isinstance(axes, dict):
            errors.append(f"{prefix}: axes는 매핑이어야 함")
            continue
        missing = [axis for axis in axis_order if not str(axes.get(axis) or "").strip()]
        unknown = sorted(set(axes) - set(axis_order))
        if missing:
            errors.append(f"{prefix}: 축 누락 {missing}")
        if unknown:
            errors.append(f"{prefix}: 미등록 축 {unknown}")
        if case.get("expect_hit") and not _expected_sources(case):
            errors.append(f"{prefix}: 양성 문항 source 좌표 없음")
    duplicates = sorted({cid for cid in ids if cid and ids.count(cid) > 1})
    if duplicates:
        errors.append(f"case id 중복 {duplicates}")
    return errors


def _axis_rows(cases: list[dict], results: dict[str, dict],
               axis_order: list[str]) -> list[dict]:
    """축/값별 통과율과 실제 Concept 진입률을 계산한다."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for case in cases:
        result = results.get(case["id"], {})
        for axis in axis_order:
            grouped[(axis, str(case["axes"][axis]))].append(result)
    rows = []
    for axis in axis_order:
        values = sorted(value for found_axis, value in grouped if found_axis == axis)
        for value in values:
            items = grouped[(axis, value)]
            rows.append({
                "axis": axis, "value": value, "total": len(items),
                "passed": sum(bool(item.get("passed")) for item in items),
                "hits": sum(bool(item.get("hit")) for item in items),
            })
    return rows


def _print_axis_analysis(cases: list[dict], results: dict[str, dict],
                         axis_order: list[str]) -> None:
    print("\n축별 분석")
    current = None
    for row in _axis_rows(cases, results, axis_order):
        if row["axis"] != current:
            current = row["axis"]
            print(f"  [{current}]")
        total = row["total"]
        print(f"    {row['value']:<22} {row['passed']}/{total}"
              f" ({row['passed'] / max(total, 1):.0%})"
              f" · 진입 {row['hits']} · 폴백 {total - row['hits']}")


def _coords(anchors) -> set[tuple[str, str]]:
    return {(str(doc_id), str(node)) for doc_id, node in anchors.source_coordinates}


def _legacy_shadow(idx) -> dict:
    """기존 207문항의 정답 근거 좌표 밖 Concept 진입을 센다.

    이 shadow는 Concept 회수율 시험이 아니라 정밀도 안전망이다. 정답 ``evidence``에
    명시된 법령·조·항·호를 실제 구조 좌표로 해소하고, Concept가 가져온 모든 Section이
    그 좌표 집합 안에 있는지만 본다. Concept가 빈손으로 하위 RAG에 넘긴 것은 실패가
    아니다. 정본이 한 조문에서 여러 법령으로 커져도 특정 제64조를 하드코딩하지 않는다.
    """
    from lawrag.core.rag import conceptfirst
    from lawrag.core.domain_graph import spanparts

    if not LEGACY.is_file():
        return {"total": 0, "entries": 0, "accepted": 0,
                "coordinate_cases": 0, "unresolved_cases": 0, "bad": []}
    blob = json.loads(LEGACY.read_text(encoding="utf-8"))
    total = entries = accepted = coordinate_cases = unresolved_cases = 0
    bad = []
    for case_no, case in blob.items():
        for pos, part in enumerate(case.get("parts") or [], 1):
            question = str(part.get("question") or "")
            evidence = str(part.get("evidence") or "")
            sections, _ = conceptfirst.retrieve(idx, question)
            anchors = spanparts.resolve_structure(idx, evidence)
            allowed = _coords(anchors)
            got = {(str(s.doc_id), str(s.node)) for s in sections}
            total += 1
            entries += bool(got)
            coordinate_cases += bool(allowed)
            unresolved_cases += bool(anchors.unresolved_locators)
            unexpected = got - allowed
            if got and not unexpected:
                accepted += 1
            if unexpected:
                bad.append({
                    "case_no": case_no, "pos": pos, "question": question,
                    "hits": [(s.doc, s.node) for s in sections],
                    "unexpected": sorted(unexpected),
                    "allowed": sorted(allowed),
                    "unresolved": list(anchors.unresolved_locators),
                })
    return {"total": total, "entries": entries, "accepted": accepted,
            "coordinate_cases": coordinate_cases,
            "unresolved_cases": unresolved_cases, "bad": bad}


def main() -> int:
    # CLI 실행에만 저장소 기본 정본을 적용한다. 이 모듈의 스키마/축 집계 함수를
    # 테스트나 다른 도구가 import했다고 전역 검색 저장소가 바뀌면 안 된다.
    os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "01_DATA" / "structure"))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", type=Path, default=DEFAULT)
    ap.add_argument("--no-shadow", action="store_true",
                    help="기존 207문항 오염 검사 생략")
    ap.add_argument("--live-llm", action="store_true",
                    help="구성된 실제 LLM으로 표시된 canary만 Span→부품 조립 (shadow 생략)")
    ap.add_argument("--case", action="append", default=[],
                    help="Concept 진입 부품검사 case id만 실행(여러 번 지정 가능)")
    ap.add_argument("--verbose", action="store_true",
                    help="실패 시 Span·LLM 제안·부품 메뉴 요약 출력")
    ap.add_argument("--output", type=Path,
                    help="문항·축·비용·성능 손잡이를 담은 평가 manifest JSON")
    ap.add_argument("--run-label", default="",
                    help="A/B 기준선·후보 실행을 구별하는 이름")
    ap.add_argument("--trial", type=int, default=1,
                    help="확률적 LLM 반복 실행 번호(기본 1)")
    args = ap.parse_args()

    from lawrag.core.rag import conceptfirst
    from lawrag.core.rag import evaluation
    from lawrag.core.rag import index as index_mod

    live_llm = None
    if args.live_llm:
        from lawrag.core import llm as llm_mod
        if not llm_mod.available():
            print(f"실제 LLM 없음 — {llm_mod.MISSING_HINT}", file=sys.stderr)
            return 2
        live_llm = llm_mod.LLM()

    spec = yaml.safe_load(args.file.read_text(encoding="utf-8")) or {}
    spec_errors = _validate_spec(spec)
    if spec_errors:
        print("Concept 진입 부품검사 스키마 오류:", file=sys.stderr)
        for error in spec_errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    idx = index_mod.current()
    cases = spec.get("cases") or []
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case.get("id") in wanted]
        missing = wanted - {case.get("id") for case in cases}
        if missing:
            print(f"없는 case id: {sorted(missing)}", file=sys.stderr)
            return 2
    elif live_llm is not None:
        cases = [case for case in cases if case.get("live_llm") is True]
        if not cases:
            print("live_llm: true인 canary가 없음", file=sys.stderr)
            return 2
    passed = 0
    results = {}
    manifest_rows = []
    for case in cases:
        log_start = len(live_llm.log) if live_llm is not None else 0
        sections, meta = conceptfirst.retrieve(idx, case["question"], llm=live_llm)
        errors = _check(case, sections, meta, live_llm=bool(live_llm))
        mark = "○" if not errors else "✗"
        print(f"  {mark} {case['id']}: {case['question']}")
        if errors:
            print("      " + " · ".join(errors))
            print(f"      fallback={meta.get('fallback')!r}")
            if args.verbose and meta.get("parts"):
                parts = meta["parts"]
                print(f"      spans={parts.get('spans')} proposals={parts.get('proposals')}")
                for menu in parts.get("menus") or []:
                    labels = [f"{p.get('label')}<{p.get('part_id')}>"
                              for p in (menu.get("parts") or [])]
                    print(f"      menu {menu.get('span', {}).get('span')!r}: "
                          + " · ".join(labels))
        else:
            passed += 1
        results[case["id"]] = {
            "passed": not errors, "hit": bool(sections),
            "fallback": str(meta.get("fallback") or ""),
        }
        exchanges = live_llm.log[log_start:] if live_llm is not None else []
        usage = {
            "calls": len(exchanges),
            "input_tokens": sum(int((x.usage or {}).get("input_tokens", 0))
                                for x in exchanges),
            "output_tokens": sum(int((x.usage or {}).get("output_tokens", 0))
                                 for x in exchanges),
            "duration_ms": sum(int(x.dur_ms) for x in exchanges),
            "ttft_ms": max((int(x.ttft_ms) for x in exchanges), default=0),
            "errors": sum(bool(x.error) for x in exchanges),
        }
        manifest_rows.append(evaluation.result_row(
            case,
            got_sources={(str(s.doc_id), str(s.node)) for s in sections},
            errors=errors, hit=bool(sections),
            fallback=str(meta.get("fallback") or ""), usage=usage,
            runtime={
                "final_contexts": len(sections),
                "context_chars": sum(len(s.text or "") for s in sections),
                "truncated_sections": sum("이후 내용 있음" in (s.text or "")
                                          for s in sections),
                "shared_cap_overflow": False,
                "channel_counts": {"concept": len(sections)},
            },
        ))
    total = len(cases)
    label = "실제 LLM 부품 canary" if live_llm else "Concept 진입 부품검사"
    print(f"\n{label} {passed}/{total} ({passed / max(total, 1):.0%})")
    _print_axis_analysis(cases, results, list(spec.get("axis_order") or []))
    if live_llm:
        calls = len(live_llm.log)
        tokens_in = sum(int((x.usage or {}).get("input_tokens", 0)) for x in live_llm.log)
        tokens_out = sum(int((x.usage or {}).get("output_tokens", 0)) for x in live_llm.log)
        duration = sum(x.dur_ms for x in live_llm.log)
        print(f"LLM 호출 {calls} · 입력 {tokens_in}tok · 출력 {tokens_out}tok"
              f" · 누적 {duration / 1000:.1f}s")

    shadow_ok = True
    report = None
    if not args.no_shadow and not live_llm and not args.case:
        report = _legacy_shadow(idx)
        bad = report["bad"]
        shadow_ok = not bad
        print(f"기존 골든 source-shadow {report['total'] - len(bad)}/{report['total']}"
              f" · Concept 진입 {report['entries']} · 좌표 적합 {report['accepted']}"
              f" · 오염 {len(bad)} · 근거 좌표 문항 {report['coordinate_cases']}"
              f" · 일부 미해소 {report['unresolved_cases']}")
        for row in bad[:12]:
            print(f"  ✗ {row['case_no']}#{row['pos']} {row['question'][:110]}")
            print(f"      hits={row['hits']} allowed={row['allowed'][:8]}")
            if row["unresolved"]:
                print(f"      unresolved={row['unresolved']}")
    elif not args.no_shadow and (live_llm or args.case):
        why = "실제 LLM 비용" if live_llm else "부분 case 실행"
        print(f"기존 207문항 shadow는 {why} 때문에 자동 생략")
    if args.output:
        manifest = evaluation.build_manifest(
            suite_path=args.file, suite=spec, rows=manifest_rows,
            mode="live_llm" if live_llm is not None else "deterministic",
            shadow=report, run_label=args.run_label, trial=args.trial,
            selected_case_ids=[str(case["id"]) for case in cases],
        )
        evaluation.write_manifest(args.output, manifest)
        print(f"평가 manifest 저장: {args.output}"
              f" · controls={manifest['controls']['fingerprint']}")
    return 0 if passed == total and shadow_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
