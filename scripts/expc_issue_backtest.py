"""쟁점 카드 백테스트 — 트리거·판정이 실제 질문을 제대로 무는지 실측.

    python scripts/expc_issue_backtest.py            # 트리거 판 (결정론, 무비용)
    python scripts/expc_issue_backtest.py --llm      # LLM 판정 판 (API 콜 67번)

사례기(법제처 해석례 색인)의 질의요지 전건이 정답 셋이다 — 과거 질문자들이
실제로 물은 문장에 spot 을 돌려서 잰다:

    발화율   질의요지 중 카드가 하나라도 뜬 비율 (트리거 어휘의 커버리지)
    적중률   발화 중 "그 사례를 인용하는 카드"가 뜬 비율 (트리거의 정밀도)

적중의 정의가 보수적이라는 점을 읽을 때 감안하라 — 주제는 맞는데 그 사례가
다른 카드(또는 해석원칙 아티클)에만 인용된 경우도 미스로 센다. 미스 목록을
사람이 읽는 이유다. 트리거·카드를 고치면 이 스크립트가 회귀 검사다
(docs/expc.md §쟁점기). 수정은 하지 않는다 — 재기만 한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.rag import wikictx                                   # noqa: E402

INDEX = REPO_ROOT / "data" / "expc" / "index.json"
ISSUE_DIR = REPO_ROOT / "data" / "wiki" / "wiki" / "쟁점"

# 같은 안건의 중복 등재 쌍 — 위키는 한쪽만 인용하므로 어느 쪽이 떠도 적중
# (정본 목록: data/wiki/wiki/index.md §데이터 유의)
TWINS = {"14-0621": "14-0438", "15-0652": "15-0641", "18-0583": "18-0261",
         "18-0481": "18-0370", "20-0563": "20-0446", "22-0422": "22-0333",
         "24-0240": "24-0239"}
TWINS.update({v: k for k, v in TWINS.items()})

CASE_CITE = re.compile(r"\[([0-9]{2}-[0-9]{4})\]\(#case/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--llm", action="store_true",
                    help="트리거 대신 LLM 판정(spot_llm)으로 잰다 — API 콜 발생")
    ap.add_argument("--misses", action="store_true", help="미스 목록 전체 출력")
    args = ap.parse_args()

    if not INDEX.is_file():
        print("색인이 없습니다 — ingest_expc.py 먼저", file=sys.stderr)
        return 2
    cases = json.loads(INDEX.read_text("utf-8"))["cases"]

    llm = None
    if args.llm:
        import os

        from core import llm as llm_mod
        llm_mod.load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("LLM 없음 — ANTHROPIC_API_KEY 필요", file=sys.stderr)
            return 2
        llm = llm_mod.LLM()

    card_cases: dict[str, set] = {}
    for p in sorted(ISSUE_DIR.glob("*.md")):
        card_cases["쟁점/" + p.stem] = set(CASE_CITE.findall(p.read_text("utf-8")))

    total = fired = hit = n_spots = 0
    misses: list[tuple] = []
    for c in cases:
        q = (c.get("issue") or "").strip()
        if not q:
            continue
        total += 1
        spots = (wikictx.spot_llm(llm, q) if args.llm else wikictx.spot(q)) or []
        n_spots += len(spots)
        if not spots:
            continue
        fired += 1
        cno = c["case_no"]
        if any(cno in card_cases.get(s["slug"], set())
               or TWINS.get(cno, "") in card_cases.get(s["slug"], set())
               for s in spots):
            hit += 1
        else:
            misses.append((cno, c["label"][:36],
                           [s["slug"].split("/", 1)[1] for s in spots]))

    mode = "LLM 판정" if args.llm else "트리거"
    print(f"[{mode}] 질의요지 {total}건 · 발화 {fired}건 ({fired / total:.0%})"
          f" · 평균 카드 {n_spots / total:.2f}"
          f" · 적중 {hit}/{fired} ({hit / fired:.0%})" if fired else
          f"[{mode}] 질의요지 {total}건 · 발화 0건")
    if misses:
        shown = misses if args.misses else misses[:8]
        print(f"\n미스 {len(misses)}건 — 판정은 사람 몫"
              f" (주제는 맞고 인용만 다른 카드일 수 있다):")
        for cno, label, slugs in shown:
            print(f"  ?? {cno} {label} → {slugs}")
        if not args.misses and len(misses) > 8:
            print(f"  … {len(misses) - 8}건 더 — --misses 로 전체")
    return 0


if __name__ == "__main__":
    sys.exit(main())
