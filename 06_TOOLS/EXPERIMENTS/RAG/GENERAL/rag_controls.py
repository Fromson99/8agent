#!/usr/bin/env python3
"""RAG 성능 손잡이 스냅샷과 구조 충돌을 확인한다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))


def main() -> int:
    from lawrag.core.rag import controls

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("audit", "snapshot"), nargs="?",
                    default="audit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = controls.snapshot()
    if args.command == "snapshot":
        print(json.dumps({"fingerprint": controls.fingerprint(rows), "values": rows},
                         ensure_ascii=False, indent=2))
        return 0
    issues = controls.audit(rows)
    literals = controls.literal_limit_candidates(ROOT)
    if args.json:
        print(json.dumps({"fingerprint": controls.fingerprint(rows), "issues": issues,
                          "unregistered_literal_candidates": literals},
                         ensure_ascii=False, indent=2))
    else:
        print(f"RAG controls {controls.fingerprint(rows)} · {len(rows)}개"
              f" · 구조 경고 {len(issues)}개"
              f" · 등록부 밖 숫자 후보 {len(literals)}개")
        for issue in issues:
            print(f"  [{issue['severity']}] {issue['code']} — {issue['message']}")
        kinds: dict[str, int] = {}
        for row in literals:
            kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        print("  숫자 후보 종류: " + " · ".join(
            f"{kind} {count}" for kind, count in sorted(kinds.items())))
        for row in literals[:12]:
            label = f" {row['name']}" if row["name"] else ""
            print(f"    {row['path']}:{row['line']} {row['kind']}{label}={row['value']}")
    return 1 if any(row["severity"] == "critical" for row in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
