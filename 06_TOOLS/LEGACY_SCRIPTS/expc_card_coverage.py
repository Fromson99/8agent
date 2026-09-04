"""쟁점 카드 커버리지 — 카드 지식이 질문 공간의 어디까지 닿는가.

    python scripts/expc_card_coverage.py

"카드가 몇 %를 덮나"를 세 자로 잰다. 발화율만 보면 착시다 — 「포섭의 경계」·
「두 법의 관문」 같은 범용 카드는 낱말 하나("등록"·"해당")로 물어 거의 아무
질문에나 발화한다. 그래서 세 겹으로 본다:

    발화     트리거가 카드를 하나라도 물었나              (넓게 — 상한)
    적중     발화한 카드 중 그 사례를 #case/ 로 인용하는 카드가 있나 (좁게 — 카드가 그 사안을 안다)
    인용됨   어느 카드든 그 사례를 인용하나               (카드 지식이 닿는 영역인가)

실측(2026-08-16): 동결 67 — 발화 97%·적중 66%. 홀드아웃 113 — 발화 91%·적중 **0%**·
인용됨 0%. 즉 홀드아웃은 카드 지식이 아예 없는 영역이고, 발화 91%는 전부 범용
카드의 오발화다. 실사용 질의는 발화 자체가 55% — 집합투자·채권 등급·ELS 같은
운용 규정 질문에 카드가 없다.

수정은 하지 않는다 — 재기만 한다. 카드를 어디에 더 써야 하는지가 이 출력이다.
카드를 쓸 때는 홀드아웃 사례로 쓰지 말 것(자 오염 — docs/GOLDEN.md §9).
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("STRUCTURE_STORE", str(REPO_ROOT / "data" / "structure"))

from lawrag.core.rag import wikictx  # noqa: E402


def _tuples() -> list:
    out = []
    for p in glob.glob(str(REPO_ROOT / "data" / "rag" / "tuples" / "*.jsonl")):
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") == "질의" and r.get("질의"):
                out.append(r["질의"])
    return list(dict.fromkeys(out))


def _fsc_issues() -> list:
    out = []
    for f in glob.glob(str(REPO_ROOT / "data" / "wiki" / "raw" / "fsc" / "*.md")):
        t = Path(f).read_text("utf-8")
        if "비조치의견서" not in t[:600]:
            continue
        m = re.search(r"## 질의요지\n(.+?)(?=\n## |\Z)", t, re.S)
        if m and "첨부한 회신문" not in m.group(1)[:90]:
            out.append(m.group(1))
    return out


def main() -> int:
    cases = json.loads((REPO_ROOT / "data" / "expc" / "index.json").read_text("utf-8"))["cases"]
    tuned_p = REPO_ROOT / "data" / "review" / "golden_tuned_cases.json"
    tuned = set(json.loads(tuned_p.read_text("utf-8"))["case_nos"]) if tuned_p.is_file() else set()
    cites: dict = {}
    for r in wikictx._issue_rows():
        for s in re.findall(r"#case/(\d+)", r["text"]):
            cites.setdefault(s, set()).add(r["slug"])

    print(f"쟁점 카드 {len(wikictx._issue_rows())}장 · 카드가 인용하는 사례 {len(cites)}건\n")
    print(f"{'집합':28} {'건':>4} {'발화':>6} {'적중':>6} {'인용됨':>6}  발화 상위 카드")

    def row(name, items, serial_of=None):
        fired = hit = cited = 0
        top = collections.Counter()
        for it in items:
            q = it if isinstance(it, str) else (it.get("issue") or "")
            h = wikictx.spot(q)
            if h:
                fired += 1
                top.update(c["title"] for c in h)
            if serial_of is not None:
                s = str(serial_of(it))
                if cites.get(s):
                    cited += 1
                if h and any(c["slug"] in cites.get(s, set()) for c in h):
                    hit += 1
        n = max(len(items), 1)
        hs = f"{hit / n:>6.0%}" if serial_of else f"{'—':>6}"
        cs = f"{cited / n:>6.0%}" if serial_of else f"{'—':>6}"
        print(f"{name:28} {len(items):>4} {fired / n:>6.0%} {hs} {cs}  "
              + " · ".join(t for t, _ in top.most_common(3)))

    row("C 동결 67", [c for c in cases if c["case_no"] in tuned], lambda c: c.get("serial"))
    row("C 홀드아웃 113", [c for c in cases if c["case_no"] not in tuned], lambda c: c.get("serial"))
    row("B 비조치의견서", _fsc_issues())
    tup = _tuples()
    row("실사용 질의 (tuples)", tup)

    miss = [q for q in tup if not wikictx.spot(q)]
    if miss:
        print(f"\n실사용 질의 미발화 {len(miss)}건 — 카드가 없는 주제 (카드 후보 재료):")
        for q in miss[:12]:
            print(f"   · {q[:72]}")
    print("\n읽는 법: 발화가 높고 적중이 낮으면 범용 카드의 오발화다. 인용됨 0% 는 카드 지식이"
          " 아예 없는 영역이다 — 거기 점수는 카드 덕이 아니라 순수 회수·판정 실력이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
