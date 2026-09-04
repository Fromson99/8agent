"""조문 프레임 추출 — 하이쿠로 조마다 누가·무엇을·누구에게·한다를 뽑는다.

    python scripts/extract_frames.py --doc 국세기본법 --doc "개인정보 보호법"
    python scripts/extract_frames.py --all
    python scripts/extract_frames.py --doc 국세기본법 --jo 제84조 -v   # 한 조만, 결과 출력

산출: data/frames/<doc_id>.jsonl (파생층 — lawrag/core/rag/frames.py 머리).
재실행은 아직 안 뽑힌 조만 다시 묻는다(--force 로 전부 다시).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "data" / "structure"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", action="append", default=[], help="문서명 (부분 일치)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--jo", default="", help="조 표면형 하나만 (예: 제84조)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    from lawrag.core import llm as llm_mod
    llm_mod.load_env()
    from lawrag.core.llm import LLM
    from lawrag.core.rag import frames, index as index_mod

    idx = index_mod.current()
    docs = [v for v in idx.docs.values()
            if a.all or any(d in v.name for d in a.doc)]
    if not docs:
        print("대상 문서 없음", file=sys.stderr)
        return 2

    if a.jo:
        v = docs[0]
        jo = next((n for n in v.nodes if (n.get("surface") or "") == a.jo
                   and "부칙" not in v.path(n["id"])), None)
        if jo is None:
            print("조 없음", file=sys.stderr)
            return 2
        fr, meta = frames.extract_jo(LLM(), v, jo)
        print(json.dumps(meta, ensure_ascii=False))
        for r in fr:
            print(json.dumps(r, ensure_ascii=False))
        return 0

    t0 = time.time()
    tot = {"jos": 0, "frames": 0, "errors": 0, "dropped": 0}
    for v in docs:
        st = frames.extract_doc(v, LLM, workers=a.workers or frames.WORKERS,
                                only_missing=not a.force)
        for k in tot:
            tot[k] += st.get(k, 0)
        print(f"{v.name[:30]:30} 조 {st['jos']:4} → 프레임 {st['frames']:5}"
              f" · 실패 {st['errors']} · 근거없음 버림 {st['dropped']}"
              f" · {st.get('sec', 0)}s", flush=True)
    print(f"\n합계 조 {tot['jos']} → 프레임 {tot['frames']} · 실패 {tot['errors']}"
          f" · 버림 {tot['dropped']} · {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
