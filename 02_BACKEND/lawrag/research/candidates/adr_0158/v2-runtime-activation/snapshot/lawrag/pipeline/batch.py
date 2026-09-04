"""배치 파이프라인 CLI — 화면의 딸깍과 같은 실행기(lawrag/core/batch)를 터미널에서.

    python -m lawrag.pipeline.batch lineup                 # 무엇이 빠졌나 (돌리지 않는다)
    python -m lawrag.pipeline.batch run                    # 빠진 것만 순서대로 전부
    python -m lawrag.pipeline.batch run --stages ingest,embed
    python -m lawrag.pipeline.batch status                 # 마지막/현재 실행

순서: ingest → structure → delegation → terms → frames(LLM) → embed → scopes.
모델이 없는 단계는 건너뛰고 이유를 남긴다. 진행은 data/pipeline/state.json 과
runs/<id>.jsonl 에 남아 화면(/pipeline/)이 같은 것을 읽는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("STRUCTURE_STORE", str(REPO_ROOT / "data" / "structure"))

from lawrag.core import batch as batch_mod  # noqa: E402


def _print_lineup(lu: dict) -> None:
    print(f"문서 {lu['documents']} · LLM {'있음' if lu.get('llm') else '없음'} · 임베딩 {'있음' if lu.get('embedding') else '없음'}")
    for i, k in enumerate(batch_mod.STAGES, 1):
        s = lu["stages"].get(k, {})
        flag = "●" if s.get("pending") else "○"
        print(f" {i}. {flag} {batch_mod.LABELS[k]:6} [{batch_mod.KIND[k]}]  빠짐 {s.get('pending', 0)}/{s.get('total', 0)}  — {s.get('note', '')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="배치 파이프라인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lineup")
    sub.add_parser("status")
    r = sub.add_parser("run")
    r.add_argument("--stages", help="쉼표 구분 (기본 전부)")
    r.add_argument("--workers", type=int)
    r.add_argument("--force", action="store_true", help="위임 간선 강제 재생성")
    a = ap.parse_args(argv)

    if a.cmd == "lineup":
        _print_lineup(batch_mod.lineup())
        return 0
    if a.cmd == "status":
        print(json.dumps(batch_mod.RUNNER.status(), ensure_ascii=False, indent=1)[:4000])
        return 0
    stages = [s.strip() for s in (a.stages or "").split(",") if s.strip()] or None
    opts = {k: v for k, v in {"workers": a.workers, "force": a.force or None}.items() if v}
    info = batch_mod.RUNNER.start(stages, opts)
    print("실행", info["run_id"], "→", " → ".join(info["stages"]))
    last = ""
    while batch_mod.RUNNER.is_running():
        st = batch_mod.RUNNER.status()
        line = " | ".join(f"{k}:{v['status']}" + (f" {v['done']}/{v['total']}" if v.get("total") else "")
                          + (f" {v['current'][:28]}" if v.get("current") else "")
                          for k, v in st["stages"].items() if v["status"] not in ("skipped",))
        if line != last:
            print("\r" + line[:200].ljust(200), end="", flush=True)
            last = line
        time.sleep(1)
    st = batch_mod.RUNNER.status()
    print("\n끝:", st["status"])
    for k, v in st["stages"].items():
        if v["status"] != "skipped" or v.get("note"):
            print(f"  {batch_mod.LABELS[k]:6} {v['status']:8} {v.get('note', '')}"
                  + (f"  오류 {len(v['errors'])}" if v.get("errors") else ""))
    return 0 if st["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
