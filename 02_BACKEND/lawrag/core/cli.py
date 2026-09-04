#!/usr/bin/env python3
"""범용 CLI — 두 국면을 그대로 노출한다 (SPEC §0).

    컴파일 (문서 종류당 1회, LLM 사용)
        python -m lawrag.core.cli compile --glossary G.yaml --samples a.pdf b.pdf \\
                                   --holdout c.pdf -o F.format.json

    런타임 (매 문서, LLM 없음)
        python -m lawrag.core.cli structurize doc.pdf --glossary G.yaml --format F.format.json \\
                                       -o var/out/doc.doc.json

    태스크
        python -m lawrag.core.cli reconcile src.doc.json tgt.doc.json --task T.yaml -o R.json

    디버깅
        python -m lawrag.core.cli inspect doc.pdf [--glossary G.yaml]

이 CLI 는 도메인을 모른다. 어떤 용어집·형식·태스크를 쓸지는 에이전트가 정한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core import (fitness_gate, format_model, glossary as glossary_mod,   # noqa: E402
                  holdout_check, parse_adapter, reconcile, structurize, term_marker)
from lawrag.core.normalize import to_jsonable                                    # noqa: E402


# ---------------------------------------------------------------------------
# 컴파일 국면
# ---------------------------------------------------------------------------

def cmd_compile(args) -> int:
    from lawrag.core import format_induce

    g = glossary_mod.load(args.glossary)
    print(f"용어집    {g.doc_type}  용어 {len(g.terms)}개 "
          f"(section {len(g.section_terms())} / fact {len(g.fact_terms())})")

    samples = []
    for p in args.samples:
        parsed = parse_adapter.parse(p)
        samples.append((p, parsed))
        print(f"파싱      {Path(p).name:<38} {parsed.parser}  요소 {len(parsed.elements)}")
        for w in parsed.warnings:
            print(f"  ! {w}")

    if args.no_llm:
        induction = format_induce.draft_without_llm(samples, g, args.doc_type)
        print("\n유도      규칙 기반 초안 (LLM 없음)")
    else:
        from lawrag.core.llm import LLM
        llm = LLM(args.model)
        print(f"\n유도      LLM {llm.model}")
        induction = format_induce.induce(samples, g, llm, args.doc_type)
        t = llm.totals()
        print(f"          호출 {t['calls']}  입력 {t['input_tokens']:,} "
              f"출력 {t['output_tokens']:,}  오류 {t['errors']}")
        if args.llm_log:
            print(f"          기록 {llm.dump_log(args.llm_log)}")

    for w in induction.warnings:
        print(f"  ! {w}")
    fmt = induction.fmt
    if fmt is None:
        print("\n형식을 만들지 못했습니다.")
        return 1

    print(f"\n형식      regex {len(fmt.regex_markers)}  term {len(fmt.term_markers)}  "
          f"신뢰도 {fmt.confidence}")
    for m in fmt.by_level():
        print(f"  regex L{m.level}  {m.id:<8} {m.pattern}")
    for t in fmt.term_markers:
        under = f"  under={t.under}" if t.under else ""
        print(f"  term  L{t.level}  {t.term}{under}")

    problems = fmt.validate_against_glossary(g)
    for p in problems:
        print(f"  ! {p}")

    # --- 적용 결과 미리보기 (§2.4-a: 추상 패턴이 아니라 결과를 보여준다) -------
    print("\n적용 결과 (샘플에 형식을 걸어 본 것)")
    for path, parsed in samples:
        doc = structurize.run(parsed, fmt, g)
        fit = fitness_gate.apply(doc, fmt, len(parsed.elements))
        print(f"  {Path(path).name}")
        print(f"    section {len(doc.sections)}  fact {len(doc.facts)}  "
              f"잔여 {len(doc.residual)}  부합 {fit.score:.0%}")
        for s in doc.sections[:args.preview]:
            head = (s.content[0].get('text', '') if s.content else '')[:46]
            print(f"      {s.section_id:<42} {head}")
        if len(doc.sections) > args.preview:
            print(f"      … 외 {len(doc.sections) - args.preview}개")

    # --- 미등록 후보 (§2.4-b) ---------------------------------------------
    if induction.candidates:
        print("\n미등록 section 용어 후보 — [section / fact / 무시] 를 판정하세요")
        for i, c in enumerate(induction.candidates, 1):
            flags = []
            if c.repeated:
                flags.append("반복")
            if c.heading_signal:
                flags.append("heading")
            print(f"  {i:2}. {c.text[:52]:<54} {'·'.join(flags) or '-':<12} 제안={c.suggest}")
            if c.reason:
                print(f"      근거: {c.reason[:96]}")
    else:
        print("\n미등록 후보 없음")

    # --- 홀드아웃 검증 (§2.5) ---------------------------------------------
    if args.holdout:
        print()
        report = holdout_check.check(args.holdout, fmt, g)
        print(holdout_check.to_text(report))
        if not report.passed and not args.force:
            print("\n형식을 확정하지 않았습니다. 불일치를 고치거나 --force 로 강제하세요.")
            return 1
    else:
        print("\n! 홀드아웃 샘플이 없습니다 — 형식 신뢰도를 낮음으로 표기합니다 (§2.1)")
        fmt.confidence = "low"

    # --- 확정 (T5) ---------------------------------------------------------
    if args.promote:
        for spec in args.promote:
            name, _, kind = spec.partition(":")
            kind = kind or "section"
            if kind == "ignore":
                continue
            g.add_term(name.strip(), [kind])
            print(f"승격      '{name.strip()}' → {kind} 용어")
        glossary_mod.save(g, args.glossary)
        print(f"용어집 저장 {args.glossary}")

    if args.out:
        p = format_model.save(fmt, args.out)
        print(f"형식 저장  {p}")
    return 0


# ---------------------------------------------------------------------------
# 런타임 국면
# ---------------------------------------------------------------------------

def cmd_routes(args) -> int:
    """등록부를 보여 준다 — '지금 무엇을 처리할 수 있는가' (§00.2)."""
    from lawrag.core import router
    print(router.describe())
    return 0


def cmd_structurize(args) -> int:
    from lawrag.core import router

    if not args.doc_type and not (args.glossary or args.format):
        # 자동 판별(detect)은 뺐다 — 유형은 호출자가 말한다.
        print("--doc-type 이 필요합니다. 등록된 유형은 `python -m lawrag.core.cli routes` 로 "
              "볼 수 있습니다 (미등록 유형 시험은 --glossary/--format 직접 지정)")
        return 1
    if args.glossary or args.format:
        # 형식·용어집 직접 지정은 **컴파일 국면 전용**이다. 아직 registry 에 등록되지
        # 않은 새 유형을 손으로 돌려 보는 통로이며, 등록된 유형은 이 길로 오면 안 된다.
        if not (args.glossary and args.format):
            print("--glossary 와 --format 은 함께 지정해야 합니다 "
                  "(또는 --doc-type 으로 등록부에 맡기세요)")
            return 1
        g = glossary_mod.load(args.glossary)
        fmt = format_model.load(args.format)
        reg = router.load()
        if fmt.doc_type in reg.doc_types() and not args.unregistered:
            print(f"'{fmt.doc_type}' 은 이미 등록부에 있습니다 — 직접 지정을 거부합니다.\n"
                  f"  등록된 유형은 반드시 등록부의 규칙으로 처리됩니다: "
                  f"--doc-type {fmt.doc_type}\n"
                  f"  (미등록 유형을 시험 중이면 --unregistered 를 붙이세요)")
            return 1
        parsed = parse_adapter.parse(args.document)
        doc = structurize.run(parsed, fmt, g)
        fit = fitness_gate.apply(doc, fmt, len(parsed.elements),
                                 args.threshold if args.threshold is not None
                                 else fitness_gate.DEFAULT_THRESHOLD)
    else:
        try:
            routed = router.route(args.document, args.doc_type,
                                  threshold=args.threshold)
        except router.RoutingError as exc:
            print(f"배차 실패\n  {exc}")
            return 1
        doc, fit, parsed, fmt = routed.doc, routed.fitness, routed.parsed, None
        print(f"배차      {routed.doc_type}  owner={routed.route.owner or '-'}")

    print(f"파서      {parsed.parser}")
    if fmt is None:
        print(f"형식      {doc.doc_type} v{doc.format_version}  [등록부]")
    else:
        print(f"형식      {fmt.doc_type} v{fmt.format_version} "
              f"(regex {len(fmt.regex_markers)} / term {len(fmt.term_markers)})  [직접 지정]")
    print(f"section   {len(doc.sections)}개   fact {len(doc.facts)}개   "
          f"잔여 {len(doc.residual)}개")
    print(f"게이트    {fit.score:.0%}  {'통과' if fit.passed else '격리'}")
    for w in fit.warnings:
        print(f"  ! {w}")

    if args.show:
        print("\nsection")
        for s in doc.sections:
            head = (s.content[0].get('text', '') if s.content else '')[:44]
            print(f"  {s.section_id:<44} p{s.page_range()}  {head}")
        print("\nfact")
        for f in doc.facts:
            mark = "△" if f.needs_review else " "
            print(f" {mark}{f.term:<18} {f.value_type:<11} "
                  f"{str(to_jsonable(f.value))[:26]:<28} ← {f.section_id}")

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc.dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장      {p}")
    return 0 if fit.passed else 2          # 격리는 실패가 아니라 별도 코드


# ---------------------------------------------------------------------------
# 태스크
# ---------------------------------------------------------------------------

def _load_doc(path: str | Path) -> structurize.Document:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    doc = structurize.Document(
        doc_type=data["doc_type"], format_version=data["format_version"],
        source_file=data["source_file"], fitness=data.get("fitness", {}),
        generated_at=data.get("generated_at", ""))
    for s in data.get("sections", []):
        doc.sections.append(structurize.Section(
            section_id=s["section_id"], marker=s.get("marker", {}), path=s.get("path", []),
            level=len(s.get("path", [])) - 1, content=s.get("content", []),
            children=s.get("children", [])))
    for f in data.get("facts", []):
        doc.facts.append(structurize.Fact(
            fact_id=f["fact_id"], term=f["term"], section_id=f["section_id"],
            value_type=f["value_type"], value=f.get("value"), raw=f.get("raw", ""),
            source=f.get("source", {}), needs_review=bool(f.get("needs_review")),
            note=f.get("note", "")))
    return doc


def cmd_reconcile(args) -> int:
    task = reconcile.load_task(args.task)
    src, tgt = _load_doc(args.source), _load_doc(args.target)
    report = reconcile.run(src, tgt, task)
    print(reconcile.to_text(report))
    if args.out:
        print(f"\n저장      {reconcile.write(report, args.out)}")
    bad = report.stats.get("VALUE_MISMATCH", 0) + report.stats.get("MISSING_IN_TARGET", 0)
    return 1 if bad else 0


def cmd_review(args) -> int:
    """격리(또는 통과) 문서의 검수 payload — 형식이 못 먹은 자리를 본다.

    require() 가 아니라 route() 를 쓴다 — 격리된 문서가 바로 이 명령의 대상이다.
    """
    from lawrag.core import review, router

    try:
        routed = router.route(args.document, args.doc_type)
    except router.RoutingError as exc:
        print(f"배차 실패\n  {exc}")
        return 1

    p = review.payload(routed)
    state = "격리" if p["quarantined"] else "통과"
    print(f"배차      {p['doc_type']}  게이트 {p['fitness']['score']:.0%} {state}")
    for w in p["fitness"]["warnings"]:
        print(f"  ! {w}")
    if not p["items"]:
        print("형식이 못 먹은 요소가 없습니다.")
    else:
        print(f"\n못 먹은 자리 {len(p['items'])}곳")
        for it in p["items"][:args.limit]:
            where = f" → {it['landed_in']}" if it.get("landed_in") else ""
            print(f"  [{it['kind']:17}] p{it['page']} {it['text'][:56]}{where}")
        if len(p["items"]) > args.limit:
            print(f"  … 외 {len(p['items']) - args.limit}곳")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\npayload → {args.output}")
    return 0


def cmd_inspect(args) -> int:
    """파싱 결과만 본다 — 형식을 만들기 전 문서를 눈으로 확인하는 통로."""
    parsed = parse_adapter.parse(args.document)
    print(f"파서      {parsed.parser}")
    print(f"요소      {len(parsed.elements)}개  (표 {parsed.stats.get('tables', 0)}, "
          f"그림 {parsed.stats.get('pictures', 0)})")
    for w in parsed.warnings:
        print(f"  ! {w}")

    marks_by_elem: dict[int, list] = {}
    if args.glossary:
        g = glossary_mod.load(args.glossary)
        for m in term_marker.mark(parsed.elements, g):
            marks_by_elem.setdefault(m.element_index, []).append(m)
        print(f"용어      {len(marks_by_elem)}개 요소에서 출현")

    for e in parsed.elements[:args.limit]:
        tag = "TABLE" if e.table else ("FIGURE" if e.is_picture else e.type)
        body = (e.table.text().splitlines()[0] if e.table
                else (f"[캡션] {e.text}" if e.is_picture and e.text else e.text))[:78]
        hits = marks_by_elem.get(e.index, [])
        mark = ("  ⟦" + ", ".join(f"{m.term}{'*' if m.is_section_candidate else ''}"
                                  for m in hits) + "⟧") if hits else ""
        print(f"  [{e.index:3}] p{e.page} {tag:16} {body}{mark}")
    if len(parsed.elements) > args.limit:
        print(f"  … 외 {len(parsed.elements) - args.limit}개 (--limit 으로 늘리세요)")
    return 0


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="core", description="용어집 기반 문서 구조화 (범용)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile", help="컴파일 국면 — 형식 만들기 (LLM)")
    c.add_argument("--glossary", required=True)
    c.add_argument("--samples", nargs="+", required=True)
    c.add_argument("--holdout", nargs="*", default=[])
    c.add_argument("-o", "--out")
    c.add_argument("--doc-type")
    c.add_argument("--model")
    c.add_argument("--llm-log")
    c.add_argument("--no-llm", action="store_true", help="규칙만으로 초안 (오프라인)")
    c.add_argument("--promote", nargs="*", help="후보 승격: '이름:section' / '이름:fact'")
    c.add_argument("--preview", type=int, default=12)
    c.add_argument("--force", action="store_true", help="홀드아웃 실패해도 저장")
    c.set_defaults(fn=cmd_compile)

    s = sub.add_parser("structurize", help="런타임 — 문서 → doc.json (등록부가 배차, LLM 없음)")
    s.add_argument("document")
    s.add_argument("--doc-type", help="처리할 문서 유형 (등록부의 doc_type — `routes` 로 확인)")
    s.add_argument("--glossary", help="[컴파일 전용] 미등록 유형을 손으로 돌려 볼 때만")
    s.add_argument("--format", help="[컴파일 전용] 미등록 유형을 손으로 돌려 볼 때만")
    s.add_argument("--unregistered", action="store_true",
                   help="등록된 유형에도 직접 지정을 허용 (권장하지 않음)")
    s.add_argument("-o", "--out")
    s.add_argument("--show", action="store_true")
    s.add_argument("--threshold", type=float, default=None)
    s.set_defaults(fn=cmd_structurize)

    rt = sub.add_parser("routes", help="등록부 보기 — 지금 무엇을 처리할 수 있는가")
    rt.set_defaults(fn=cmd_routes)

    r = sub.add_parser("reconcile", help="정합성 비교 — doc.json 두 개")
    r.add_argument("source", help="정답 문서의 doc.json")
    r.add_argument("target", help="대상 문서의 doc.json")
    r.add_argument("--task", required=True)
    r.add_argument("-o", "--out")
    r.set_defaults(fn=cmd_reconcile)

    i = sub.add_parser("inspect", help="파싱 결과 보기")
    i.add_argument("document")
    i.add_argument("--glossary")
    i.add_argument("--limit", type=int, default=60)
    i.set_defaults(fn=cmd_inspect)

    v = sub.add_parser("review", help="검수 — 형식이 못 먹은 자리 (격리 문서 진단)")
    v.add_argument("document")
    v.add_argument("--doc-type", default=None, help="생략하면 자동 판별")
    v.add_argument("-o", "--output", default=None, help="payload JSON 저장 경로")
    v.add_argument("--limit", type=int, default=30)
    v.set_defaults(fn=cmd_review)

    args = ap.parse_args(argv)
    # print 는 CLI 의 화면이고, logging 은 core 모듈의 관측이다 — 파일에도 남긴다.
    from lawrag.core import logbook
    logbook.setup("cli")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
