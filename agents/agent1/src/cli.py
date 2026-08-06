#!/usr/bin/env python3
"""agent1 — 파일 두 개를 받아 대사한다.

    python agents/agent1/src/cli.py run --contract <pdf> --prospectus <pdf> [-o report.json]
    python agents/agent1/src/cli.py scope  <pdf> --kind contract|prospectus --section "별지1/..."
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline                                        # noqa: E402
import service                                         # noqa: E402


def cmd_run(args) -> int:
    report = pipeline.run(args.contract, args.prospectus, args.rules,
                          save_docs=args.save_docs)
    print(pipeline.to_text(report))
    if args.out:
        print(f"\n저장      {pipeline.write(report, args.out)}")
    return 1 if report.stats.get("틀림", 0) else 0


def cmd_scope(args) -> int:
    """범위 좁히기만 — LLM 없이 무엇이 넘어가는지 눈으로 본다."""
    import scope as scope_mod
    # 문서 종류는 --kind 로 말할 뿐, 어떤 형식·용어집으로 자를지는 등록부가 정한다.
    if args.kind == "prospectus":
        s, label = service.structurize_prospectus(args.document), "투자설명서"
    else:
        s, label = service.structurize_contract(args.document), "계약서"
    sc = scope_mod.build(s.doc, label, args.section, terms=args.term or None,
                         glossary=s.glossary, max_rows=args.limit)
    print(scope_mod.to_table(sc))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent1")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="계약서·투자설명서 두 파일을 대사")
    r.add_argument("--contract", required=True)
    r.add_argument("--prospectus", required=True)
    r.add_argument("--rules")
    r.add_argument("-o", "--out")
    r.add_argument("--save-docs", action="store_true")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("scope", help="범위 좁히기 결과만 보기 (LLM 없음)")
    s.add_argument("document")
    s.add_argument("--kind", choices=["contract", "prospectus"], default="contract")
    s.add_argument("--section", nargs="+", required=True)
    s.add_argument("--term", nargs="*")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(fn=cmd_scope)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
