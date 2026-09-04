"""회수 단독 벤치 — **LLM 없이** 회수기만 잰다.

    python scripts/retr_bench.py              # 골든 v2 정답 66마디 전수
    python scripts/retr_bench.py --case 19-0152 -v

## 왜 필요한가

오늘(2026-08-17) 회수 개선을 세 번 시도해 세 번 "왜 안 됐는지 모른다"로 끝났다.
원인은 하나다 — **회수의 입력이 매번 다르다.** 회수는 쟁점 문장으로 검색하는데,
쟁점 도출은 같은 사실에서 41%만 재현된다. 그래서 회수기를 고쳐도 그 효과가
쟁점 요동에 묻힌다. 숫자로는 절망적이었다: 같은 코드 두 판의 회수 폭이 2개인데
확장이 만든 효과가 0개였다.

이 벤치는 **쟁점을 고정**한다. 정답 마디가 속한 조의 제목·본문 앞머리를 질의로
써서 build_norms 를 직접 부른다. LLM 을 안 부르므로 결정론이고, 30초에 끝난다.
회수기를 갈아가며 "정답 마디 66개 중 몇 개를 데려오나"만 본다.

**한계를 알고 써라.** 여기서 오르는 것이 파이프라인 전체에서 오른다는 보장은
없다 — 실제 쟁점 문장은 이 질의와 다르다. 이 벤치는 "회수기가 이 마디에 닿을
능력이 있는가"를 재는 것이고, "쟁점이 그 질의를 만들어 주는가"는 별개다.
그래도 능력이 없으면 능력을 먼저 만들어야 한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "01_DATA" / "structure"))
MARKED = ROOT / "01_DATA" / "review" / "marked.json"


def _query(idx, law: str, jo: str, node_id) -> str:
    """정답 마디의 조 제목 + 본문 앞머리 — 쟁점이 이상적으로 냈을 질의의 대역."""
    from lawrag.core.rag import wikictx
    key = wikictx._pack(law)
    for v in idx.docs.values():
        if wikictx._pack(v.name) != key:
            continue
        n = v.by_id.get(node_id) or v.by_id.get(int(node_id)) if str(node_id).isdigit() \
            else v.by_id.get(node_id)
        if n is None:
            continue
        title = (n.get("title") or "").strip()
        body = (v.section_text(n, cap=300) or "").replace("\n", " ")
        return f"{title} {body}".strip()[:300]
    return f"{law} {jo}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    from lawrag.core.rag import index as index_mod, wikictx
    from lawrag.core.casereview.model import Issue, ReviewState
    from lawrag.core.casereview import pipeline as rp

    idx = index_mod.current()
    M = json.loads(MARKED.read_text("utf-8"))["cases"]
    cases = [a.case] if a.case else sorted(k for k, v in M.items() if v.get("decisive_full"))

    tot = hit = 0
    for c in cases:
        want = M[c]["decisive_full"]
        got_any = 0
        for d in want:
            q = _query(idx, d["law"], d.get("jo", ""), d.get("node_id"))
            st = ReviewState(question=q)
            issue = Issue(question=q, gate="")
            norms = rp.build_norms(idx, issue, st)
            # 회수한 구역과 그 하위 전부
            cover = set()
            for n in list(norms) + list(st.glossary):
                v = idx.docs.get(n.doc_id)
                if v is None:
                    continue
                stack = [n.node]
                while stack:
                    x = stack.pop()
                    cover.add((wikictx._pack(v.name), str(x)))
                    stack.extend(k["id"] for k in v.nodes if k.get("parent") == x)
            ok = (wikictx._pack(d["law"]), str(d.get("node_id"))) in cover
            tot += 1
            hit += ok
            got_any += ok
            if a.verbose or not ok:
                print(f"  {'○' if ok else '✗'} {c} {d['law']} {d.get('jo')}"
                      f"{d.get('hang_ho') or ''} [{d.get('node_id')}]"
                      + ("" if ok else f"\n      질의: {q[:90]}"))
        print(f"{c}  {got_any}/{len(want)}")
    print(f"\n=== 회수 단독 {hit}/{tot} ({hit/max(tot,1):.0%}) — LLM 없음 · 결정론 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
