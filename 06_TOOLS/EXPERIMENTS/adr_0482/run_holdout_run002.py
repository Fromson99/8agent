"""Run-002: preserve run-001 and fix only its missing baseline receipt adapter."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
CAND = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0482/source-first-fsc-hard10-run002"
BASE_RUNNER = ROOT / "06_TOOLS/EXPERIMENTS/adr_0482/run_holdout.py"

spec = importlib.util.spec_from_file_location("adr0482_run001", BASE_RUNNER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def pin():
    design = read(ADR / "artifacts/frozen-design-run-002.json")
    for raw, value in design["file_hashes"].items():
        if sha(ROOT / raw) != value:
            raise RuntimeError("Frozen run-002 input changed: " + raw)
    candidate = read(CAND / "candidate.json")
    revision = next(row for row in candidate["revisions"] if row["revision_id"] == "rev-001")
    for row in revision["files"]:
        if sha(ROOT / row["frozen_path"]) != row["snapshot_sha256"]:
            raise RuntimeError("Frozen run-002 candidate changed")
    frozen = CAND / "revisions/rev-001/snapshot/02_BACKEND"
    sys.path.insert(0, str(frozen))
    sys.path.insert(1, str(ROOT / "02_BACKEND"))
    import lawrag.research
    lawrag.research.__path__.insert(0, str(frozen / "lawrag/research"))
    return design


class FixedGeminiProvider(base.GeminiProvider):
    def record_local(self, value):
        path = self.client.output / ("local-" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16] + ".json")
        write(path, {"method": "SOURCE_ONLY", "output": value})
        return {"id": "receipt:" + path.stem, "contract": "provider.receipt", "path": str(path), "sha256": sha(path)}


base.GeminiProvider = FixedGeminiProvider


def run_one(case, arm, fixture):
    from lawrag.research.experiment_client import GeminiExperimentClient
    out = ADR / "artifacts/run-002" / case["case_id"] / arm
    out.mkdir(parents=True, exist_ok=False)
    client = GeminiExperimentClient(ROOT, out / "calls", max_calls=14, max_output_tokens=2800)
    started = time.monotonic()
    output = {"case_id": case["case_id"], "arm": arm, "model": base.MODEL, "main_wiring": "unchanged", "error": None}
    try:
        result, stages, trace = base.baseline(case, fixture, client) if arm == "baseline" else base.source_first(case, fixture, out, client)
        output.update(result=result, stages=stages)
        write(out / "execution.json", trace)
    except Exception as exc:
        output["error"] = {"type": type(exc).__name__, "message": str(exc)}
    output.update(physical_calls=client.calls, usage=client.usage, seconds=round(time.monotonic() - started, 3))
    write(out / "result.json", output)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    design = pin()
    fixture = read(ADR / "product-cases.json")
    if not args.execute:
        print(json.dumps({"preflight": "pass", "network_calls": 0, "cases": len(fixture["cases"]), "arms": design["arms"], "model": base.MODEL}))
        return
    runroot = ADR / "artifacts/run-002"
    if runroot.exists():
        raise RuntimeError("run-002 exists; never overwrite or repeat")
    runroot.mkdir(parents=True)
    summary = {"schema_version": "fsc-hard10-paired-results-v1", "model": base.MODEL, "cases": {}, "started_at": time.time(), "run_id": "run-002", "run-001_preserved": True}
    for index, case in enumerate(fixture["cases"]):
        order = ["baseline", "source-first"] if index % 2 == 0 else ["source-first", "baseline"]
        summary["cases"][case["case_id"]] = {}
        for arm in order:
            result = run_one(case, arm, fixture)
            summary["cases"][case["case_id"]][arm] = result
            write(runroot / "results.partial.json", summary)
            print(json.dumps({"case": case["case_id"], "arm": arm, "calls": result["physical_calls"], "error": result["error"], "seconds": result["seconds"]}, ensure_ascii=False), flush=True)
    summary["finished_at"] = time.time()
    write(runroot / "results.json", summary)
    print(json.dumps({"complete": True, "case_count": len(summary["cases"]), "run_id": "run-002"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
