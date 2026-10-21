"""Read-only catalogue/structure inspection using the sealed batch's real service."""
import argparse
import csv
import importlib.util
import os
from pathlib import Path
import sys

from basis_quick import Runner, atomic, plain, read, require, sha


def inspect(app, batch, ids=None):
    from semantic_runtime.basis_links.contracts import BasisError
    from semantic_runtime.basis_links.grouping import inventory

    rows, who = batch.catalogue(app, "risk_team")
    binding = batch.selected_binding(app, who)
    failures = []
    if ids is not None:
        require(len(ids) == len(set(ids)) and set(ids) <= {r["document_id"] for r in rows},
                "선택한 최신 내규의 권한/목록이 변경되었습니다.")
        rows = [r for r in rows if r["document_id"] in ids]
        for row in rows:
            try:
                inventory(app.state.pipeline.store, row["document_id"])
            except BasisError as exc:
                if exc.code != "BASIS_STRUCTURE":
                    raise
                failures.append({**{k: row[k] for k in ("document_id", "name", "source_artifact_sha256")},
                                 "status": "failed", "phase": "plan", "code": exc.code,
                                 "message": str(exc), "research_attempted": False})
    require(batch.selected_binding(app, who) == binding, "구조 확인 도중 데이터/권한 결속이 바뀌었습니다.")
    return {"schema": "basis-structure-preflight-v1", "binding": binding,
            "documents": rows, "failures": failures}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--transfer", type=Path, required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--catalogue", type=Path)
    a = parser.parse_args()
    root = a.root.resolve(strict=True)
    specs = read(Path(__file__).with_name("RUNNERS.json"))["runners"]
    spec = next(s for s in specs if s["folder"] == a.package)
    runner = Runner(root, a.transfer, spec)
    require(sha(root / "00_SYSTEM/PIPELINE.json") == spec["pipeline_sha256"], "선택 코드 변경")
    requirements = read(runner.package / "tools/CODE_REQUIREMENTS.json")
    for base, files in ((root, requirements["checkout"]), (runner.package / "tools", requirements["tool"])):
        for name, expected in files.items():
            require(sha(base / name) == expected, "CODE_GATE: " + name)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root / "02_BACKEND"), str(root)]
    os.environ.update(LAWRAG_WORKSPACE_ROOT=str(root), LAWRAG_TOOL_WORKSPACE_ROOT=str(root),
                      SOURCE_PROVIDER_PROJECT_ROOT=str(root), PYTHONDONTWRITEBYTECODE="1")
    pipeline = read(root / "00_SYSTEM/PIPELINE.json")
    implementation = pipeline["profiles"]["legal-rag"]["nodes"][0]["parameters"]["term_agent"]["implementation"]
    require(implementation == "legal-agent-unified-v6", "검증된 R3 legal RAG가 필요합니다.")
    os.environ["GENOS_RAG_IMPLEMENTATION"] = implementation
    module_spec = importlib.util.spec_from_file_location("_preflight_batch", runner.package / "tools/basis_batch.py")
    batch = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(batch)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    batch.resources(a.output.parent)
    with batch.heartbeat({"phase": "structure-preflight"}):
        app = batch.boot(root)
        result = inspect(app, batch, a.ids)
    if a.catalogue:
        path = plain(a.catalogue)
        require(not path.exists(), "기존 전체 목록을 덮어쓰지 않습니다.")
        with path.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["document_id", "name", "chars", "source_artifact_sha256", "is_latest"])
            writer.writeheader()
            writer.writerows(result["documents"])
            stream.flush()
            os.fsync(stream.fileno())
    atomic(a.output, result, "receipt_sha256")
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
