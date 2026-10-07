"""User-facing CLI for the evidence-grounded legal ontology lifecycle.

    python -m lawrag.pipeline.ontology status
    python -m lawrag.pipeline.ontology validate
    python -m lawrag.pipeline.ontology run
    python -m lawrag.pipeline.ontology run --stages legal_graph,definition_projections --yes
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from lawrag.core import batch as batch_mod
from lawrag.ontology import contract_report, lifecycle_snapshot, load_catalog


def _print_snapshot(snapshot: dict) -> None:
    print(f"{snapshot['name']}  [{snapshot['schema_version']}]")
    print("입력 → 추출 → 변환 → 사용 → 재구조화")
    for phase in snapshot["phases"]:
        flag = "●" if phase["status"] == "attention" else "◇" if phase["status"] == "gated" else "○"
        print(f"\n{flag} {phase['label']} — {phase['purpose']}")
        for stage_id in phase["stages"]:
            stage = snapshot["stages"][stage_id]
            policy = {"automatic": "자동", "explicit": "명시", "manual_only": "승인"}[stage["execution_policy"]]
            pending = f"빠짐 {stage['pending']}/{stage['total']}" if stage["total"] else "대상 없음"
            print(f"   {stage['label']:<18} [{policy}·{stage['mode']}] {pending} — {stage['note']}")
    action = snapshot.get("next_action")
    if action:
        print(f"\n다음 동작: {action['label']} ({action['policy']})")
    else:
        print("\n다음 동작: 자동/명시 단계에 빠진 항목이 없습니다. release gate는 별도 승인입니다.")


def _requested_stages(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    catalog = load_catalog()
    aliases = {
        str(stage["id"]): stage.get("runner_stage")
        for stage in catalog["stages"]
        if stage.get("runner_stage")
    }
    known = set(batch_mod.STAGES)
    result: list[str] = []
    for value in (part.strip() for part in raw.split(",")):
        if not value:
            continue
        stage = aliases.get(value, value)
        if stage not in known:
            raise ValueError(f"모르는 실행 단계: {value}")
        if stage not in result:
            result.append(stage)
    return result or None


def _run(stages: list[str] | None, *, confirmed: bool, json_output: bool) -> int:
    report = contract_report()
    if not report["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    requested = stages or list(batch_mod.AUTO_STAGES)
    explicit = [stage for stage in requested if stage not in batch_mod.AUTO_STAGES]
    if explicit and not confirmed:
        print(
            "명시 단계는 immutable generation을 만들거나 전체 계약을 검사합니다: "
            + ", ".join(explicit)
            + "\n확인했다면 --yes를 붙여 다시 실행하세요.",
            file=sys.stderr,
        )
        return 2
    info = batch_mod.RUNNER.start(requested)
    if not json_output:
        print("실행", info["run_id"], "→", " → ".join(info["stages"]))
    while batch_mod.RUNNER.is_running():
        if not json_output:
            status = batch_mod.RUNNER.status()
            current = next(
                (
                    (key, value)
                    for key, value in status["stages"].items()
                    if value["status"] == "running"
                ),
                None,
            )
            if current:
                key, value = current
                print(
                    f"\r{batch_mod.LABELS[key]} {value['done']}/{value['total']} "
                    f"{value.get('current', '')[:60]}",
                    end="",
                    flush=True,
                )
        time.sleep(0.5)
    status = batch_mod.RUNNER.status()
    if json_output:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"\n끝: {status['status']}")
        for stage in status["requested"]:
            value = status["stages"][stage]
            print(f"  {batch_mod.LABELS[stage]:<12} {value['status']:<8} {value.get('note', '')}")
    return 0 if status["status"] == "done" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="법률 온톨로지 생명주기 파이프라인")
    sub = parser.add_subparsers(dest="command", required=True)
    status_parser = sub.add_parser("status", help="다섯 단계의 현재 상태를 읽기만 한다")
    status_parser.add_argument("--json", action="store_true")
    validate_parser = sub.add_parser("validate", help="스키마·stage mapping·Projection을 검증한다")
    validate_parser.add_argument("--json", action="store_true")
    run_parser = sub.add_parser("run", help="기존 증분 실행기를 통해 선택 단계를 실행한다")
    run_parser.add_argument("--stages", help="쉼표 구분 stage ID; 기본은 기존 자동 증분 단계")
    run_parser.add_argument("--yes", action="store_true", help="무거운 명시 단계를 확인한다")
    run_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "status":
        snapshot = lifecycle_snapshot()
        if args.json:
            print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        else:
            _print_snapshot(snapshot)
        return 0
    if args.command == "validate":
        report = contract_report()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for check in report["checks"]:
                print(f"{'PASS' if check['ok'] else 'FAIL'}  {check['id']} — {check['target']}")
                for error in check["errors"]:
                    print(f"      {error}")
            print("\n온톨로지 계약 검증 통과" if report["ok"] else "\n온톨로지 계약 검증 실패")
        return 0 if report["ok"] else 1
    try:
        stages = _requested_stages(args.stages)
    except ValueError as exc:
        parser.error(str(exc))
    return _run(stages, confirmed=args.yes, json_output=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
