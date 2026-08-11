#!/usr/bin/env python3
"""RAG 질문셋 러너 — bench/questions.yaml 의 질문을 /v1/rag/ask 로 돌린다.

    .venv/bin/python scripts/rag_bench.py                 # 전체 셋
    .venv/bin/python scripts/rag_bench.py --set bond-grade
    .venv/bin/python scripts/rag_bench.py --base http://localhost:5566

질문마다: answerable · 답 첫 글자 시간(TTFT, 스트리밍 실측) · 합성 시간 ·
총 시간 · 근거 수 · 지문/교정 수를 표로 낸다. 원자료는
bench/last_results.json 에 남는다 — 질문셋을 고친 뒤 다시 돌려 전후를
비교하는 것이 이 파일의 쓰임새다. 모든 질의는 서버의 진단 튜플로도 쌓여
/rag/debug.html 에서 전모(답 전문·회수 구역)를 다시 볼 수 있다.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def ask(base: str, question: str, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        f"{base}/v1/rag/ask", method="POST",
        data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5566")
    ap.add_argument("--file", default=str(ROOT / "bench" / "questions.yaml"))
    ap.add_argument("--set", dest="only", default=None,
                    help="이 id 의 셋만 돌린다")
    args = ap.parse_args()

    spec = yaml.safe_load(Path(args.file).read_text(encoding="utf-8"))
    rows: list[dict] = []
    for s in spec.get("sets", []):
        if args.only and s.get("id") != args.only:
            continue
        for q in s.get("questions", []):
            t0 = time.perf_counter()
            try:
                out = ask(args.base, q)
                err = out.get("error", "")
            except Exception as exc:
                out, err = {}, f"{type(exc).__name__}: {exc}"
            total_ms = int((time.perf_counter() - t0) * 1000)
            tm = out.get("timing") or {}
            row = {
                "set": s.get("id"), "질문": q, "qid": out.get("qid"),
                "answerable": out.get("answerable"),
                "ttft_ms": tm.get("answer_ttft_ms"),
                "answer_ms": tm.get("answer_ms"),
                "total_ms": total_ms,
                "근거": len(out.get("refs") or []),
                "지문": len(out.get("discards") or []),
                "교정": len(out.get("fixes") or []),
                "탐험": (out.get("recovery") or {}).get("rungs_fired"),
                "답": (out.get("answer") or "")[:120],
                "error": err,
            }
            rows.append(row)
            mark = "○" if row["answerable"] else ("×" if err else "—")
            print(f"[{row['set']}] {mark} ttft {row['ttft_ms'] or '?':>5}ms"
                  f" · 총 {total_ms:>6}ms · 근거 {row['근거']}"
                  f" · 지문 {row['지문']} · 교정 {row['교정']} | {q}"
                  + (f"  !! {err}" if err else ""), flush=True)

    out_path = ROOT / "bench" / "last_results.json"
    out_path.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "rows": rows}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    n_ok = sum(1 for r in rows if r["answerable"])
    ttfts = [r["ttft_ms"] for r in rows if r["ttft_ms"]]
    print(f"\n질문 {len(rows)} · 답변됨 {n_ok}"
          + (f" · TTFT 중앙값 {sorted(ttfts)[len(ttfts)//2]}ms"
             f" (최소 {min(ttfts)} · 최대 {max(ttfts)})" if ttfts else "")
          + f"\n원자료: {out_path}")


if __name__ == "__main__":
    main()
