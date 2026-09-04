"""구조 해석기 CLI.

    python -m lawrag.core.structure.cli interpret 계약서.pdf
    python -m lawrag.core.structure.cli interpret KSB.pdf --json out.json --ledger .ledger.json
    python -m lawrag.core.structure.cli signals            # 관리소에 무엇이 등록됐나
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core import parse_adapter                                    # noqa: E402
from lawrag.core.structure import fingerprint, pipeline, registry        # noqa: E402
from lawrag.core.structure.model import Block, Node, StructureResult     # noqa: E402


def _tree_lines(nodes: list[Node], prefix: str = "") -> list[str]:
    out: list[str] = []
    for i, n in enumerate(nodes):
        last = i == len(nodes) - 1
        out.append(f"{prefix}{'└─' if last else '├─'} L{n.level} {n.surface}"
                   f"  [{n.family}] b{n.block_idx}-{n.span[1]} p{n.page}")
        out += _tree_lines(n.children, prefix + ("   " if last else "│  "))
    return out


def report(r: StructureResult, tree_limit: int = 60) -> str:
    out = [f"구조 해석  {r.doc}",
           f"  적합도 {r.fitness_score:.0%} ({'통과' if r.fitness_passed else '미달'})"
           f"  티어 {r.tier}  DP 총점 {r.stats.get('dp_total')}",
           f"  블록 {r.stats.get('blocks')}  후보 {r.stats.get('candidates')}"
           f"  활성 {r.stats.get('activated')}  가지치기 {r.stats.get('pruned')}",
           "",
           f"사다리 (fingerprint: {r.fingerprint.key()})"]
    for rung in r.ladder.rungs:
        out.append(f"  L{rung.level}  {', '.join(sorted(rung.families)):<40} "
                   f"reg {rung.reg_score:.2f}")
    for note in r.ladder.notes:
        out.append(f"  · {note}")
    if r.ladder.unregistered:
        out.append(f"  미등재: {', '.join(sorted(r.ladder.unregistered))}")

    out += ["", "트리"]
    lines = _tree_lines(r.tree)
    out += lines[:tree_limit]
    if len(lines) > tree_limit:
        out.append(f"  … 외 {len(lines) - tree_limit}줄 (--tree-limit 으로 늘리세요)")

    llm = r.stats.get("llm")
    if llm:
        out += ["", f"LLM 배치 1콜 — 물음 {llm['asked']}건 → 구조 {len(llm['structure'])}, "
                    f"인용 {len(llm['mention'])}, 보류 {len(llm['unsure'])}; "
                    f"실제 변경 {llm['changed']}건"]
        for n in llm["notes"]:
            out.append(f"  · {n}")
    if r.residual:
        head = "남은 잔여" if llm else "애매한 잔여 — 문서당 1콜 배치 대상"
        out += ["", f"{head} ({len(r.residual)}건)"]
        out += [f"  ? {x}" for x in r.residual[:10]]
    if r.warnings:
        out += ["", "경고"] + [f"  ! {w}" for w in r.warnings]
    return "\n".join(out)


def _pairs(items):
    out = []
    for x in items or []:
        a, _, b = x.partition(">")
        if not b:
            raise SystemExit(f"--order 는 '상위>하위' 형태여야 합니다 (받은 값 '{x}')")
        out.append((a.strip(), b.strip()))
    return out


def cmd_interpret(args) -> int:
    ledger = fingerprint.Ledger.load(args.ledger) if args.ledger else None
    llm = None
    if args.llm:
        from lawrag.core.llm import LLM
        llm = LLM(model=args.model)
    hint = [g.split(",") for g in args.ladder] if args.ladder else None

    rc = 0
    for path in args.documents:
        parsed = parse_adapter.parse(path)
        for w in parsed.warnings:
            print(f"  ! {Path(path).name}: {w}")
        r = pipeline.interpret(Block.from_elements(parsed.elements),
                               doc=Path(path).name, lang=args.lang, ledger=ledger,
                               root=args.root, families=args.families,
                               ladder_hint=hint, partial_order=_pairs(args.order),
                               llm=llm)
        print(report(r, args.tree_limit))
        print()
        if args.audit:
            print("감사 로그")
            for line in r.audit_log[:args.audit]:
                print(f"  {line}")
            print()
        if args.json:
            p = Path(args.json)
            if len(args.documents) > 1:
                p = p.with_name(f"{p.stem}.{Path(path).stem}{p.suffix}")
            p.write_text(json.dumps(r.dump(), ensure_ascii=False, indent=2),
                         encoding="utf-8")
            print(f"해석 리포트: {p}")
        if not r.fitness_passed:
            rc = 1
    if ledger:
        ledger.save()
    if llm:
        print(f"LLM 사용량: {llm.totals()}")
        if args.llm_log:
            print(f"LLM 기록: {llm.dump_log(args.llm_log)}")
    return rc


def cmd_signals(args) -> int:
    print(registry.default().describe())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lawrag.core.structure",
                                 description="구조 해석기 (SPEC: docs/structure_interpreter_SPEC.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("interpret", help="문서 → 구조 트리 (S0~S5)")
    i.add_argument("documents", nargs="+")
    i.add_argument("--lang", default="ko")
    i.add_argument("--root", help="좌표 최상위 계열 (예: kr_article)")
    i.add_argument("--families", nargs="*", help="어휘 제한 (예: dot_number roman)")
    i.add_argument("--ladder", nargs="*", metavar="L",
                   help="층 지정. 층마다 하나씩, 같은 층은 쉼표 "
                        "(예: --ladder dot_number:1 dot_number:2 circled)")
    i.add_argument("--order", nargs="*", metavar="A>B",
                   help="특정 쌍의 순서만 지정 (예: --order kr_장>kr_절 kr_절>kr_article)")
    i.add_argument("--llm", action="store_true",
                   help="잔여를 문서당 배치 1콜로 해소 (없으면 결정론만)")
    i.add_argument("--model", help="LLM 모델 (기본: ANTHROPIC_MODEL)")
    i.add_argument("--llm-log", help="LLM 요청·응답 기록 저장 경로")
    i.add_argument("--ledger", help="fingerprint 장부 경로 (재현빈도 판정)")
    i.add_argument("--json", help="해석 리포트 JSON 저장")
    i.add_argument("--audit", type=int, default=0, help="감사 로그 N줄 출력")
    i.add_argument("--tree-limit", type=int, default=60)
    i.set_defaults(fn=cmd_interpret)

    s = sub.add_parser("signals", help="관리소 등록 현황")
    s.set_defaults(fn=cmd_signals)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
