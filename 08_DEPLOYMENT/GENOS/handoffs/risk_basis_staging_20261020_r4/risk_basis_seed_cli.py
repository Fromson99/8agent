"""Stage four user-fixed links in the existing JSON review batch; no SQLite writes."""
import argparse
import getpass
from pathlib import Path
import sys
import time

from semantic_runtime.basis_links.contracts import require
from . import basis_batch_artifacts as artifacts
from . import risk_basis_staging


def settings(root):
    root = Path(root).resolve(strict=True)
    value = artifacts.read_json(root / "00_SYSTEM/GENOS_SERVING_PATHS.json")
    require(Path(value["generation"]).is_absolute() and Path(value["runtime"]).is_absolute(),
            "RISK_STAGE_PATH", "기존 generation/runtime의 절대 경로가 필요합니다.")
    generation = artifacts.plain(value["generation"])
    runtime = artifacts.plain(value["runtime"])
    pipeline = artifacts.read_json(root / "00_SYSTEM/PIPELINE.json")
    config = (root, pipeline["profiles"]["legal-rag"]["nodes"][0]["parameters"]["term_agent"])
    return generation, runtime, config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "stage"))
    parser.add_argument("--root", type=Path, default=Path.home() / "DEV")
    parser.add_argument("--job", type=Path, help="같은 stage-plan 작업 폴더. 기본값은 공통 검토 배치와 동일")
    parser.add_argument("--operator", default=getpass.getuser())
    args = parser.parse_args(argv)
    job = None
    try:
        generation, runtime, config = settings(args.root)
        job = artifacts.plain(args.job or runtime / "basis-batch/pilot-review-20261020-r1")
        def check():
            require(settings(args.root) == (generation, runtime, config),
                    "RISK_STAGE_CONTEXT", "저장 직전에 GENOS 설정이 변경됐습니다.", 409)
        result = risk_basis_staging.stage(job, generation, runtime, args.operator,
            inspect=args.action == "inspect", config=config, context_check=check)
        artifacts.emit("risk.fixed." + args.action, **result)
        return 0
    except Exception as exc:
        record = {"status": "FAILED_OR_UNCONFIRMED", "action": args.action,
                  "error_type": type(exc).__name__, "code": getattr(exc, "code", None), "message": str(exc),
                  "next": "같은 검토 job으로 stage를 다시 실행하면 JSON receipt를 확인합니다. 직접 SQLite 대체 경로는 없습니다."}
        if job is not None and job.is_dir():
            artifacts.atomic(job / ("RISK_FIXED_FAILURE_" + str(time.time_ns()) + ".json"), record)
        artifacts.emit("risk.fixed.failed", **record)
        return 1


if __name__ == "__main__":
    sys.exit(main())
