"""정의 조 → 용어 상하관계 표 (하이쿠).

    python scripts/extract_taxonomy.py --doc 국세기본법 --doc "개인정보 보호법"
    python scripts/extract_taxonomy.py --all

산출: data/taxonomy/<doc_id>.jsonl (lawrag/core/rag/taxonomy.py 머리).
"""
from __future__ import annotations
import argparse, os, sys, time
from pathlib import Path
ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "01_DATA" / "structure"))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    from lawrag.core import llm as llm_mod; llm_mod.load_env()
    from lawrag.core.llm import LLM
    from lawrag.core.rag import index as index_mod, taxonomy
    idx = index_mod.current()
    docs = [v for v in idx.docs.values() if a.all or any(d in v.name for d in a.doc)]
    t0 = time.time(); tot = {"jos": 0, "terms": 0, "errors": 0}
    for v in docs:
        st = taxonomy.extract_doc(v, LLM, workers=a.workers or taxonomy.WORKERS, only_missing=not a.force)
        for k in tot: tot[k] += st.get(k, 0)
        print(f"{v.name[:30]:30} 정의 조 {st['jos']:3} → 용어 {st['terms']:4} · 실패 {st['errors']} · {st.get('sec',0)}s", flush=True)
    print(f"\n합계 조 {tot['jos']} → 용어 {tot['terms']} · 실패 {tot['errors']} · {time.time()-t0:.0f}s")
    return 0

if __name__ == "__main__":
    sys.exit(main())
