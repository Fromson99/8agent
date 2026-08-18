"""골든을 **다시 만든다** — 180건에서 쓸 만한 후보만 빠르게 추린다.

    python scripts/golden_pick.py                  # 후보 순위 + 요약
    python scripts/golden_pick.py --top 40 --write # data/review/golden_v2.json 저장

## 왜 다시 만드나

원문 마킹 38건(data/review/marked.json)에서 골든의 결함이 흩어진 버그가 아니라
**구조적**임이 드러났다 — 시점충돌 82% · 창고결손 76% · 구어파손 74% ·
판례필요 58%. 결함 없는 사례는 38건 중 2건이었다. 고쳐 쓰는 것보다 **좋은 것만
골라 다시 세우는** 쪽이 빠르다.

## 고르는 기준 (전부 기계가 본다 — LLM 안 부른다)

감점 방식이다. 점수가 낮을수록 좋은 후보다.

    창고결손   회답·이유의 「법령」이 창고에 없다        건당 -30  ← 치명적
    조 부재    인용한 (법,조)에서 조가 창고에 없다        건당 -12  ← 개정으로 밀림
    구법 표현  "구 「…법」" · "폐지"                       -15
    판례필요   대법원·헌재·법제처 선례 인용                -10
    다부       질의요지가 "가." "나." 로 갈린다            -10
    중복       같은 해석례가 두 안건번호로 등록됨          제외
    오래됨     연도가 오래될수록 개정 위험이 크다   (2026-연도) × -1.5
    조문 특정  회답이 조까지 대면 정답이 뚜렷하다          건당 +6 (최대 +18)

## 무엇을 만들지 않나

구어 질문은 여기서 만들지 않는다. 골라낸 뒤 사람·에이전트가 태깅하면서
docs/RETRIEVAL.md 8-4 의 다섯 규칙에 맞게 새로 쓴다 — 지금 구어는 "일상어
변환"이 아니라 81% 요약이라 쟁점·전제·주체가 함께 날아갔다.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "data" / "structure"))

OUT = ROOT / "data" / "review" / "golden_v2.json"
_PREC = re.compile(r"대법원|헌법재판소|선고\s*\d{2,4}[가-힣]+\d+|\d{2}-\d{4}")
_OLDLAW = re.compile(r"구\s*「|폐지되기?\s*전|법률\s*제\d+호로\s*폐지")
_PARTS = re.compile(r"(?:^|\n|\s)가\.\s.{5,}(?:\n|\s)나\.\s", re.S)


def cited(case: dict) -> tuple:
    """(법령 집합, (법,조) 집합) — 회답과 이유를 모두 읽는다."""
    text = (case.get("answer") or "") + "\n" + str(case.get("reason") or "")
    laws, pairs, cur = set(), set(), ""
    for m in re.finditer(r"「([^」]+)」|(제\d+조(?:의\d+)?)", text):
        if m.group(1):
            cur = m.group(1).strip()
            if len(cur) > 3 and not cur.startswith("제"):
                laws.add(cur)
        elif cur:
            pairs.add((cur, m.group(2)))
    return laws, pairs


def score(cases: list) -> list:
    from lawrag.core.rag import index as index_mod, wikictx
    idx = index_mod.current()
    have = {wikictx._pack(v.name): v for v in idx.docs.values()}

    by_hash = collections.defaultdict(list)
    for c in cases:
        k = hashlib.md5(((c.get("answer") or "") + str(c.get("reason") or "")).encode()).hexdigest()
        by_hash[k].append(c["case_no"])
    dup = set()
    for g in by_hash.values():
        dup |= set(sorted(g)[1:])            # 첫째만 남기고 나머지는 제외

    rows = []
    for c in cases:
        no = c["case_no"]
        laws, pairs = cited(c)
        text = (c.get("answer") or "") + "\n" + str(c.get("reason") or "")
        miss = sorted(l for l in laws if wikictx._pack(l) not in have)
        gone = []
        for law, jo in pairs:
            v = have.get(wikictx._pack(law))
            if v is not None and not any((n.get("surface") or "") == jo for n in v.nodes):
                gone.append(f"{law} {jo}")
        prec = bool(_PREC.search(str(c.get("reason") or "")))
        old = bool(_OLDLAW.search(text))
        parts = bool(_PARTS.search(c.get("issue") or ""))
        year = 2000 + int(no[:2]) if no[:2].isdigit() else 2000

        s = 0
        s -= 30 * len(miss)
        s -= 12 * len(set(gone))
        s -= 15 if old else 0
        s -= 10 if prec else 0
        s -= 10 if parts else 0
        s -= max(0, 2026 - year) * 1.5
        s += min(18, 6 * len(pairs))
        rows.append({
            "case_no": no, "score": round(s, 1), "year": year,
            "dup": no in dup, "store_missing": miss, "jo_gone": sorted(set(gone))[:4],
            "needs_precedent": prec, "old_law": old, "multi_part": parts,
            "n_laws": len(laws), "n_jo": len(pairs),
            "laws": sorted(laws)[:4],
            "title": (c.get("issue") or "")[:70].replace("\n", " "),
        })
    rows = [r for r in rows if not r["dup"]]
    rows.sort(key=lambda r: -r["score"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    from scripts.review_golden import _cases
    cases = _cases()
    by_no = {c["case_no"]: c for c in cases}
    rows = score(cases)

    print(f"=== 골든 {len(cases)}건 → 중복 제외 {len(rows)}건 · 상위 {a.top}건을 고른다 ===\n")
    print(f"{'순위':<4}{'사례':<9}{'점수':>7}  {'연도':<6}{'결손':<5}{'조부재':<7}{'판례':<5}{'제목'}")
    for i, r in enumerate(rows[:a.top], 1):
        print(f"{i:<4}{r['case_no']:<9}{r['score']:>7}  {r['year']:<6}"
              f"{len(r['store_missing']):<5}{len(r['jo_gone']):<7}"
              f"{'예' if r['needs_precedent'] else '  ':<5}{r['title'][:44]}")

    top = rows[:a.top]
    clean = [r for r in top if not r["store_missing"] and not r["jo_gone"]
             and not r["needs_precedent"] and not r["multi_part"]]
    print(f"\n  상위 {a.top}건 중 결함 신호가 하나도 없는 사례: {len(clean)}건")
    print("   ", " · ".join(r["case_no"] for r in clean))
    print(f"\n  전체 분포: 창고결손 없음 {sum(1 for r in rows if not r['store_missing'])}건 · "
          f"조부재 없음 {sum(1 for r in rows if not r['jo_gone'])}건 · "
          f"판례불요 {sum(1 for r in rows if not r['needs_precedent'])}건")

    if a.write:
        payload = {"_설명": "골든 v2 후보 — scripts/golden_pick.py 가 고른 상위 셋. "
                            "tags 는 UI(/golden) 또는 에이전트가 채운다.",
                   "picked": [{**r,
                               "issue": by_no[r["case_no"]].get("issue"),
                               "answer": by_no[r["case_no"]].get("answer"),
                               "tags": None} for r in top]}
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
        print(f"\n  → {OUT}  ({len(top)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
