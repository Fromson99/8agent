"""법령 조문을 항·호까지 펴서 보여준다 — 정답 마킹(사람·에이전트)용 열람 도구.

    python scripts/lawlook.py --law "공공기관의 정보공개" --jo 제2조   # 한 조를 편다
    python scripts/lawlook.py --law "개인정보 보호법" --list          # 조 목록
    python scripts/lawlook.py --case 08-0411                        # 사례(질의·회답·이유)

회수 평가의 자를 다시 만들 때 쓴다: 회답이 **결정 근거로 쓴 마디**와 **전제로만
인용한 마디**는 다른데, 정규식으로 뽑은 지금 자(want_articles)는 그 둘을 못 가른다
— 10-0055 는 "정보가 아닌 경우"를 전제로 깔고 묻는데 그 전제 인용(제2조)이
정답 조문으로 세어졌다. 마디마다 [id] 를 달아 두므로 그 id 로 마킹한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "data" / "structure"))


def _idx():
    from core.rag import index as index_mod
    return index_mod.current()


def find_doc(idx, needle: str) -> list:
    """법령명 일부로 문서를 찾는다 — 공백·낫표는 무시한다(짧은 이름 우선)."""
    from core.rag import wikictx
    key = wikictx._pack(needle)
    hits = [v for v in idx.docs.values() if key in wikictx._pack(v.name)]
    return sorted(hits, key=lambda v: len(v.name))


def show_jo(v, jo: str, depth: int = 3) -> None:
    """한 조를 항·호·목까지 들여쓰기로 편다."""
    top = [n for n in v.nodes if (n.get("surface") or "") == jo]
    if not top:
        print(f"  (없음: {v.name} {jo})")
        return
    for n in top:
        print(f"\n■ {v.name} {jo}  [{n['id']}]  {n.get('title') or ''}")

        def walk(node: dict, ind: int = 1) -> None:
            kids = [k for k in v.nodes if k.get("parent") == node["id"]]
            own = v.section_text(node, cap=100000) or ""
            if not kids:
                print("  " * ind + f"[{node['id']}] {own.strip()[:800]}")
                return
            first = kids[0].get("surface") or ""
            head = own.split(first)[0] if first and first in own else own
            print("  " * ind + f"[{node['id']}] {head.strip()[:500]}")
            if ind >= depth:
                print("  " * (ind + 1) + f"… 하위 {len(kids)}개 생략 (--depth 로 더)")
                return
            for k in kids:
                walk(k, ind + 1)

        walk(n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--law", default="", help="법령명 일부")
    ap.add_argument("--jo", default="", help="제2조 (쉼표로 여럿)")
    ap.add_argument("--list", action="store_true", help="그 법의 조 목록")
    ap.add_argument("--case", default="", help="사례 원문 (질의요지·회답·이유)")
    ap.add_argument("--depth", type=int, default=3)
    a = ap.parse_args()

    if a.case:
        from scripts.review_golden import _cases
        c = {x["case_no"]: x for x in _cases()}.get(a.case)
        if not c:
            print("그런 사례가 없습니다", file=sys.stderr)
            return 2
        col = json.loads((ROOT / "data/review/colloquial.json").read_text("utf-8"))
        col = col.get("items", col)
        print(f"=== {a.case} ===")
        print(f"\n[구어 질문 — 실제로 시스템에 넣은 것]\n{col.get(a.case, '(없음)')}")
        print(f"\n[질의요지]\n{c.get('issue') or ''}")
        print(f"\n[회답]\n{c.get('answer') or ''}")
        reason = c.get("reason") or c.get("reasons") or ""
        if reason:
            print(f"\n[이유]\n{str(reason)[:8000]}")
        return 0

    idx = _idx()
    if not a.law:
        for v in sorted(idx.docs.values(), key=lambda x: x.name):
            print(" ", v.name)
        return 0

    docs = find_doc(idx, a.law)
    if not docs:
        print(f"'{a.law}' 에 걸리는 법령이 없습니다", file=sys.stderr)
        return 2
    v = docs[0]
    if len(docs) > 1:
        print("※ " + str(len(docs)) + "개 걸림 — 첫째를 편다: "
              + " · ".join(d.name for d in docs[:5]))
    if a.list or not a.jo:
        jos = [n for n in v.nodes
               if re.match(r"^제\d+조(?:의\d+)?$", n.get("surface") or "")]
        print(f"\n■ {v.name} — 조 {len(jos)}개")
        for n in jos:
            print(f"  {n['surface']:<12} {(n.get('title') or '')[:40]}")
        return 0
    for jo in a.jo.split(","):
        show_jo(v, jo.strip(), a.depth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
