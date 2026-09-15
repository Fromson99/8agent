#!/usr/bin/env python3
"""실제 제품 흐름 여러 판을 합쳐 전체 RAG 검증 범위와 품질을 판정한다.

부품 골든 점수를 합산하지 않는다. ``ask``와 ``legal_review``의 실제 E2E
manifest만 받고, 최종 답·근거 게이트와 채널/단계 관측 범위를 별도로 보고한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
DEFAULT_SPEC = ROOT / "01_DATA" / "review" / "e2e_portfolio_v1.json"


def _gate(metric: str, actual: float, rule: dict[str, Any]) -> dict[str, Any]:
    passed = True
    if "min" in rule:
        passed = passed and actual >= float(rule["min"])
    if "max" in rule:
        passed = passed and actual <= float(rule["max"])
    return {"metric": metric, "actual": actual, **rule, "passed": passed}


def _coverage(required: list[str], totals: dict[str, int]) -> dict[str, Any]:
    observed = [key for key in required if int(totals.get(key, 0)) > 0]
    return {
        "required": required, "observed": observed,
        "missing": [key for key in required if key not in observed],
        "rate": round(len(observed) / len(required), 6) if required else 1.0,
        "totals": dict(sorted(totals.items())),
    }


def build(spec: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    from lawrag.core.rag import evaluation, promote

    artifact_rows = []
    primary_artifact_id = str(spec.get("primary_artifact_id") or "")
    by_flow: dict[str, list[dict[str, Any]]] = {}
    problems: list[str] = []
    for item in spec.get("artifacts") or []:
        path = root / str(item["path"])
        if not path.is_file():
            problems.append(f"missing_artifact:{item['id']}")
            continue
        manifest = evaluation.load_manifest(path)
        flow = str(item["flow"])
        actual_flow = str((manifest.get("run") or {}).get("mode") or "")
        if actual_flow != flow:
            problems.append(f"flow_mismatch:{item['id']}:{actual_flow}")
        metrics = dict((manifest.get("summary") or {}).get("metrics") or {})
        gates = [_gate(key, float(metrics.get(key, 0.0)), dict(rule))
                 for key, rule in (item.get("gates") or {}).items()]
        if any(not gate["passed"] for gate in gates):
            problems.append(f"quality_gate:{item['id']}")
        row = {
            "id": str(item["id"]), "flow": flow, "path": str(path),
            "primary": str(item["id"]) == primary_artifact_id,
            "suite": str((manifest.get("suite") or {}).get("name") or ""),
            "cases": int(metrics.get("cases", 0)), "gates": gates,
            "passed": all(gate["passed"] for gate in gates),
        }
        artifact_rows.append(row)
        by_flow.setdefault(flow, []).append(manifest)

    required_flows = [str(x) for x in spec.get("required_flows") or []]
    missing_flows = [flow for flow in required_flows if flow not in by_flow]
    problems.extend(f"missing_flow:{flow}" for flow in missing_flows)
    flow_rows: dict[str, Any] = {}
    for flow in required_flows:
        manifests = by_flow.get(flow) or []
        ids: set[str] = set()
        trials: set[int] = set()
        channel_totals: dict[str, int] = {}
        stage_totals: dict[str, int] = {}
        for manifest in manifests:
            ids.update(str(x) for x in (manifest.get("suite") or {}).get("case_ids") or [])
            trials.add(int((manifest.get("run") or {}).get("trial", 1)))
            for result in manifest.get("results") or []:
                runtime = result.get("runtime") or {}
                for key, count in (runtime.get("channel_counts") or {}).items():
                    channel_totals[str(key)] = channel_totals.get(str(key), 0) + int(count)
                for key, count in (runtime.get("stage_counts") or {}).items():
                    stage_totals[str(key)] = stage_totals.get(str(key), 0) + int(count)
        channels = _coverage(
            [str(x) for x in (spec.get("required_channels") or {}).get(flow, [])],
            channel_totals)
        stages = _coverage(
            [str(x) for x in (spec.get("required_stages") or {}).get(flow, [])],
            stage_totals)
        canary_min = int((spec.get("canary_minimum_unique_cases") or {}).get(flow, 0))
        release_min = int((spec.get("release_minimum_unique_cases") or {}).get(flow, 0))
        if len(ids) < canary_min:
            problems.append(f"canary_cases:{flow}:{len(ids)}/{canary_min}")
        if channels["missing"]:
            problems.append(f"channel_coverage:{flow}:{','.join(channels['missing'])}")
        if stages["missing"]:
            problems.append(f"stage_coverage:{flow}:{','.join(stages['missing'])}")
        flow_rows[flow] = {
            "unique_cases": len(ids), "trials": sorted(trials),
            "channel_coverage": channels, "stage_coverage": stages,
            "canary_case_target": canary_min, "release_case_target": release_min,
            "release_case_ready": len(ids) >= release_min,
            "release_trial_ready": len(trials) >= int(spec.get("release_minimum_trials", 3)),
        }

    lexicon_values = []
    for manifest in by_flow.get("legal_review") or []:
        value = float(((manifest.get("summary") or {}).get("metrics") or {}).get(
            "lexicon_cache_coverage", 0.0))
        if value:
            lexicon_values.append(value)
    readiness_values = {
        "memory_active_rows": len(promote.active()),
        "lexicon_cache_coverage": min(lexicon_values) if lexicon_values else 0.0,
    }
    readiness = [_gate(key, float(readiness_values.get(key, 0.0)), dict(rule))
                 for key, rule in (spec.get("readiness_gates") or {}).items()]
    for gate in readiness:
        if not gate["passed"]:
            problems.append(f"readiness:{gate['metric']}")

    release_gaps = []
    for flow, row in flow_rows.items():
        if not row["release_case_ready"]:
            release_gaps.append(
                f"release_cases:{flow}:{row['unique_cases']}/{row['release_case_target']}")
        if not row["release_trial_ready"]:
            release_gaps.append(
                f"release_trials:{flow}:{len(row['trials'])}/"
                f"{int(spec.get('release_minimum_trials', 3))}")
    release_ready = (not problems and not release_gaps and all(
        row["release_case_ready"] and row["release_trial_ready"]
        for row in flow_rows.values()))
    return {
        "schema_version": 1, "name": str(spec.get("name") or ""),
        "role": str(spec.get("role") or ""),
        "primary_artifact_id": primary_artifact_id,
        "canary_verdict": "pass" if not problems else "fail",
        "release_ready": release_ready, "problems": problems,
        "release_gaps": release_gaps,
        "artifacts": artifact_rows, "flows": flow_rows, "readiness": readiness,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    report = build(spec)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"전체 프로세스 canary: {report['canary_verdict']}"
              f" · release_ready={report['release_ready']}")
        for flow, row in report["flows"].items():
            channel_text = (f"{row['channel_coverage']['rate']:.1%}"
                            if row["channel_coverage"]["required"] else "n/a")
            print(f"  {flow}: {row['unique_cases']}건"
                  f" · 채널 {channel_text}"
                  f" · 단계 {row['stage_coverage']['rate']:.1%}")
        for row in report["artifacts"]:
            failed = [gate["metric"] for gate in row["gates"] if not gate["passed"]]
            print(f"  {'CORE ' if row.get('primary') else ''}{row['id']}: "
                  f"{'PASS' if row['passed'] else 'FAIL'}"
                  + (f" ({', '.join(failed)})" if failed else ""))
        for problem in report["problems"]:
            print(f"  ! {problem}")
        for gap in report["release_gaps"]:
            print(f"  · {gap}")
    return 0 if report["canary_verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
