#!/usr/bin/env python3
"""Offline holdout for the ADR-0167 KOFIA attachment-body fallback."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path


TARGET_NAMES = {
    "금융투자회사의 컴플라이언스 매뉴얼 공통·증권·선물편",
    "금융투자회사의 컴플라이언스 매뉴얼 Ⅲ편(자산운용)",
}
EXPECTED = {
    "금융투자회사의 컴플라이언스 매뉴얼 공통·증권·선물편": "5a4df93bbbb084a8",
    "금융투자회사의 컴플라이언스 매뉴얼 Ⅲ편(자산운용)": "89789427b5b7899a",
}


def _load(path: Path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("adr0167_frozen_batch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    candidate = args.candidate.resolve()
    started = time.perf_counter()
    module = _load(candidate)
    with tempfile.TemporaryDirectory(prefix="adr0167-kofia-") as temporary:
        previous = os.environ.get("STRUCTURE_STORE")
        os.environ["STRUCTURE_STORE"] = temporary
        try:
            selected = [
                row for row in module.ingest_targets() if row["name"] in TARGET_NAMES
            ]
            outputs = []
            for target in selected:
                result = module._ingest_one(target)
                document = Path(temporary) / result["doc_id"]
                outputs.append(
                    {
                        "name": target["name"],
                        "via": target["via"],
                        "source_suffix": Path(target["path"]).suffix.lower(),
                        "doc_id": result["doc_id"],
                        "expected_doc_id": EXPECTED[target["name"]],
                        "meta_exists": (document / "meta.json").is_file(),
                        "result_exists": (document / "result.json").is_file(),
                        "result_sha256": hashlib.sha256(
                            (document / "result.json").read_bytes()
                        ).hexdigest(),
                    }
                )
        finally:
            if previous is None:
                os.environ.pop("STRUCTURE_STORE", None)
            else:
                os.environ["STRUCTURE_STORE"] = previous
    passed = len(outputs) == 2 and all(
        row["via"] == "file"
        and row["source_suffix"] == ".hwp"
        and row["doc_id"] == row["expected_doc_id"]
        and row["meta_exists"]
        and row["result_exists"]
        for row in outputs
    )
    receipt = {
        "schema_version": "adr0167-kofia-body-fallback-holdout-v1",
        "result": "pass" if passed else "fail",
        "candidate": candidate.relative_to(root).as_posix(),
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "outputs": outputs,
        "usage": {"llm_calls": 0, "embedding_calls": 0, "network_calls": 0},
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
