"""회수 모드 비교 — 용어 사다리(auto) vs 벡터 우선(vector), LLM 없이.

    python -m core.rag.bench "질의1" "질의2" …
    python -m core.rag.bench --file queries.txt

질의마다 두 모드의 착지(문서·구역·경로)를 나란히 놓는다. 어느 쪽이 옳은지는
사람이(나중엔 golden 이) 판정한다 — 이 도구는 판정하지 않고 보여만 준다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def compare(query: str) -> dict:
    from core.rag import index as index_mod
    from core.rag import vecfirst
    from core.rag.search import search

    idx = index_mod.current()
    r = search(idx, query)
    auto = [{"kind": h.kind, "value": h.value[:40], "doc": h.doc,
             "node": h.node,
             "path": (idx.docs[h.doc_id].path(h.node)
                      if h.doc_id in idx.docs and h.node is not None else "")}
            for h in r.hits[:5]]
    sections, vmeta = vecfirst.retrieve(idx, query)
    vec = [{"kind": s.kind, "matched": s.matched, "doc": s.doc,
            "node": s.node, "path": s.path} for s in sections[:8]]
    return {"query": query, "auto_mode": r.mode, "auto": auto,
            "vector": vec, "vector_meta": vmeta}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m core.rag.bench",
                                 description=__doc__.split("\n")[0])
    ap.add_argument("queries", nargs="*")
    ap.add_argument("--file", type=Path, default=None,
                    help="질의 파일 — 한 줄에 하나")
    args = ap.parse_args(argv)
    queries = list(args.queries)
    if args.file:
        queries += [x.strip() for x in
                    args.file.read_text(encoding="utf-8").splitlines()
                    if x.strip()]
    if not queries:
        ap.error("질의를 주세요")

    for q in queries:
        c = compare(q)
        print(f"\n■ {q}")
        print(f"  [용어 사다리 · {c['auto_mode']}]")
        for h in c["auto"] or [{}]:
            if h:
                print(f"    {h['kind']:>3} {h['path'] or h['value']}"
                      f"  ({h['doc'][:18]} n={h['node']})")
            else:
                print("    (빈손)")
        print(f"  [벡터 우선 · 진입 {len(c['vector_meta']['entries'])}"
              f" · 깊이 {c['vector_meta']['depth']}]")
        for s in c["vector"] or [{}]:
            if s:
                print(f"    {s['kind']:>3} {s['path']}"
                      f"  ({s['doc'][:18]} n={s['node']}) {s['matched']}")
            else:
                print("    (빈손)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
