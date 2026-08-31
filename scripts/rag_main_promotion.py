#!/usr/bin/env python3
"""Prepare, validate, apply, inspect, or roll back MAIN RAG promotion plans."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core.rag import main_promotion


def _switch(raw: str) -> tuple[str, bool]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("switch must be KEY=on|off")
    key, value = raw.split("=", 1)
    normalized = value.strip().lower()
    if normalized not in {"on", "off", "true", "false", "1", "0"}:
        raise argparse.ArgumentTypeError("switch value must be on or off")
    return key.strip(), normalized in {"on", "true", "1"}


def _code_artifact(raw: str) -> tuple[Path, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("code artifact must be PATH=GUARD_SWITCH")
    path, guard = raw.rsplit("=", 1)
    return Path(path), guard.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="freeze a promotion plan without changing MAIN")
    prepare.add_argument("--source-manifest", required=True, type=Path)
    prepare.add_argument("--arm", required=True)
    prepare.add_argument("--switch", action="append", type=_switch, default=[])
    prepare.add_argument("--code-artifact", action="append", type=_code_artifact, default=[])
    prepare.add_argument("--validation-receipt", action="append", type=Path, default=[])
    prepare.add_argument("--actor", required=True)
    prepare.add_argument("--output", required=True, type=Path)

    check = sub.add_parser("check", help="validate a frozen plan against current MAIN")
    check.add_argument("--plan", required=True, type=Path)

    apply = sub.add_parser("apply", help="atomically promote a valid plan to MAIN")
    apply.add_argument("--plan", required=True, type=Path)
    apply.add_argument("--actor", required=True)
    apply.add_argument("--approval-note", required=True)
    apply.add_argument("--confirm-main", action="store_true")

    rollback = sub.add_parser("rollback", help="roll back the latest active promotion")
    rollback.add_argument("--promotion-id", required=True)
    rollback.add_argument("--actor", required=True)
    rollback.add_argument("--note", required=True)
    rollback.add_argument("--confirm-main", action="store_true")

    sub.add_parser("status", help="show current MAIN generation and provenance")
    return parser


def _load(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "prepare":
            switch_changes = dict(args.switch)
            if len(switch_changes) != len(args.switch):
                raise ValueError("switch keys must be unique")
            plan = main_promotion.prepare_plan(
                args.source_manifest,
                args.arm,
                switch_changes=switch_changes,
                code_artifacts=args.code_artifact,
                validation_receipts=args.validation_receipt,
                actor=args.actor,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2) + "\n", "utf-8")
            print(args.output)
            return 0
        if args.command == "check":
            errors = main_promotion.validate_plan(_load(args.plan))
            for error in errors:
                print(f"ERROR: {error}")
            if not errors:
                print(f"OK: {args.plan}")
            return 1 if errors else 0
        if args.command == "apply":
            result = main_promotion.apply_plan(
                _load(args.plan), actor=args.actor, approval_note=args.approval_note,
                confirm_main=args.confirm_main)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "rollback":
            result = main_promotion.rollback(
                args.promotion_id, actor=args.actor, note=args.note,
                confirm_main=args.confirm_main)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({
            "state": main_promotion.load_state(),
            "runtime": main_promotion.runtime_provenance(),
            "receipts": main_promotion.read_receipts(),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
