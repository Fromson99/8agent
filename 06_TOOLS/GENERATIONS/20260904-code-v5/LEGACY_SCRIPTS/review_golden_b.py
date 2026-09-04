"""B트랙(적법성 검토) 골든 — 금융위 비조치의견서로 요건표 파이프라인을 잰다.

    python scripts/review_golden_b.py --label            # 판정 라벨링 (1회, 캐시)
    python scripts/review_golden_b.py --limit 20         # 실행 + 채점
    python scripts/review_golden_b.py --report           # 재집계 (무비용)

C트랙 골든(review_golden.py)이 "이 조문이 무슨 뜻이냐"를 재는 자라면, 이것은
"이 서비스 설계가 법에 맞나"를 재는 자다. 비조치의견서가 정확히 그 모양이다 —
회사가 **계획한 행위**를 적어 물으면 금융위가 "그렇게 하면 조치하지 않겠다 /
그건 안 된다 / 이 조건이면 된다"로 답한다(2026-08-16 실측: raw/fsc 187건,
관련 법령이 코퍼스와 겹친다 — 전자금융감독규정 65·금융투자업규정 26·신정법 25).

C트랙 자와 다른 점 셋:
  · 입력은 사실이 아니라 **설계**(Fact.tense=계획) — track="적법성"
  · 정답은 극성이 아니라 **적법성 판정** — 비조치(가능) / 조건부 비조치 / 조치(불가)
  · 시스템 출력은 해석 판정이 아니라 **Verdict.conclusion** (가능·불가·조건부·판단보류)
    — 요건표 기계(포섭)가 실제 B트랙에서 맞는지는 이 자가 처음 잰다. 어제 그
    기계를 C트랙에 오용하고 있던 걸 발견했지만, 정작 제 트랙에서 검증된 적이 없다.

같은 규율: 홀드아웃 오염 금지(이 187건은 위키 카드 컴파일에 쓰지 않는다 — 카드가
이미 있는 영역이라 더 조심), 라벨은 정의부터, 점수보다 귀속.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(REPO_ROOT))
for _k, _v in (("STRUCTURE_STORE", "01_DATA/structure"),
               ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
               ("GLOSSARY_STORE", "01_DATA/glossary.json"),
               ("RAG_LINKS_STORE", "01_DATA/links.json")):
    os.environ.setdefault(_k, str(REPO_ROOT / _v))

RAW_DIR = REPO_ROOT / "01_DATA" / "wiki" / "raw" / "fsc"
OUT_DIR = REPO_ROOT / "01_DATA" / "review"
LABELS = OUT_DIR / "golden_b_labels.json"
LAST = OUT_DIR / "golden_b_last.json"

LABEL_MODEL = "claude-opus-5"
# ── 정답 공간의 정의 ─────────────────────────────────────────────────────────
# 비조치의견서 회답은 셋 중 하나다:
#   비조치     "그 설계대로 하면 조치하지 않겠다 / 위반이 아니다 / 가능하다"
#   조건부     "이 조건·전제를 지키면 비조치" — 회답이 조건을 결론의 일부로 단다
#              ("다만 …를 마련하시기 바랍니다" 같은 권고는 조건이 아니라 부가 — 비조치)
#   조치       "그 설계는 위반이다 / 허용되지 않는다 / 불가"
# 시스템 결론(가능·조건부·불가·판단보류)과의 대응: 가능↔비조치, 조건부↔조건부,
# 불가↔조치, 판단보류는 유보로 따로 센다.
LABEL_SYSTEM = (
    "너는 금융위원회 비조치의견서 회신의 **결론**을 뽑는 라벨러다 — 이 라벨이 "
    "시스템 채점의 자(尺)라 정확도가 전부다.\n"
    "verdict 는 셋 중 하나: 비조치(설계대로 해도 조치하지 않는다·위반 아니다·"
    "가능하다), 조건부(회신이 **결론의 일부로** 조건·전제를 달아 그것을 지킬 때만 "
    "비조치라 할 때 — '다만 …하시기 바랍니다' 같은 부가 권고는 조건이 아니라 "
    "비조치다), 조치(위반이다·허용되지 않는다·불가). 판단을 유보한 회신은 "
    "confidence=low 로 두고 verdict 는 가장 가까운 것으로.\n"
    "evidence 는 결론 문장을 회신에서 **그대로** 옮긴다. conditions 에는 조건부일 때 "
    "그 조건을 짧게(없으면 빈 배열). confidence 는 결론 문장이 명시적이면 high."
)
LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["비조치", "조건부", "조치"]},
        "evidence": {"type": "string"},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["verdict", "evidence", "conditions", "confidence"],
    "additionalProperties": False,
}
CONCLUSION_TO_VERDICT = {"가능": "비조치", "조건부": "조건부", "불가": "조치"}


def _llm():
    from lawrag.core import llm as llm_mod
    llm_mod.load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return llm_mod.LLM()


def _sec(text: str, name: str) -> str:
    m = re.search(rf"## {name}\n(.+?)(?=\n## |\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def _stub(s: str) -> bool:
    return (not s) or ("첨부한 회신문" in s and len(s) < 90)


def cases() -> list:
    """raw/fsc 의 비조치의견서 중 질의·판정 텍스트가 온전한 것."""
    out = []
    for f in sorted(glob.glob(str(RAW_DIR / "*.md"))):
        t = Path(f).read_text("utf-8")
        if "비조치의견서" not in t[:600]:
            continue
        q, a, why = _sec(t, "질의요지"), _sec(t, "회답"), _sec(t, "이유")
        if _stub(q) or (_stub(a) and _stub(why)):
            continue
        m = re.search(r"관련: (.+)", t[:800])
        laws = [x.strip() for x in (m.group(1) if m else "").split("·") if x.strip()]
        out.append({"case_no": Path(f).stem, "title": t.split("\n")[0][2:],
                    "issue": q, "answer": (a if not _stub(a) else "") + "\n" + why,
                    "laws": laws})
    return out


# ---------------------------------------------------------------- 라벨링
def label(llm, cs: list, force: bool = False) -> dict:
    have = {} if force else (json.loads(LABELS.read_text("utf-8")) if LABELS.is_file() else {})
    todo = [c for c in cs if c["case_no"] not in have]
    print(f"라벨 {len(have)}건 보유 · {len(todo)}건 새로 매긴다 ({LABEL_MODEL})")
    for i, c in enumerate(todo, 1):
        out = llm.structured("golden_b.label", LABEL_SYSTEM,
                             f"[질의요지]\n{c['issue'][:1500]}\n\n[회신]\n{c['answer'][:3000]}",
                             LABEL_SCHEMA, max_tokens=600, effort="medium",
                             model=LABEL_MODEL)
        if out:
            have[c["case_no"]] = out
        if i % 20 == 0:
            print(f"  … {i}/{len(todo)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LABELS.write_text(json.dumps(have, ensure_ascii=False, indent=1), "utf-8")
    from collections import Counter
    print(f"라벨 {len(have)}건 저장 — 분포 {dict(Counter(v['verdict'] for v in have.values()))}"
          f" · low {sum(1 for v in have.values() if v['confidence'] == 'low')}건")
    return have


# ---------------------------------------------------------------- 실행
def run_one(llm, idx, case: dict) -> dict:
    from lawrag.core.casereview import pipeline as rp
    from lawrag.core.rag import wikictx
    t0 = time.perf_counter()
    st = rp.run(llm, idx, case["issue"][:2000], track="적법성")
    concl = [v.conclusion for v in st.verdicts]
    # 쟁점별 결론을 사안 하나로 접는다 — conclude() 와 같은 보수성
    if not concl:
        overall = "판단보류"
    elif "불가" in concl:
        overall = "불가"
    elif all(c == "가능" for c in concl):
        overall = "가능"
    elif all(c == "판단보류" for c in concl):
        overall = "판단보류"
    else:
        overall = "조건부"
    got_docs = {wikictx._pack(n.doc) for n in st.norms}
    want = {wikictx._pack(l) for l in case.get("laws") or []}
    return {"case_no": case["case_no"], "title": case["title"][:60],
            "issues": len(st.issues), "norms": len(st.norms), "subs": len(st.subs),
            "unclear": len(st.unresolved()),
            "conclusion": overall, "verdict": CONCLUSION_TO_VERDICT.get(overall, "유보"),
            "want_laws": sorted(want), "got_laws": sorted(want & got_docs),
            "sec": round(time.perf_counter() - t0, 1)}


# ---------------------------------------------------------------- 채점
def score(rows: list, labels: dict) -> None:
    from collections import Counter
    n = len(rows)
    if not n:
        print("실행 결과가 없습니다 — --limit 로 먼저 돌리세요")
        return
    fired = sum(1 for r in rows if r["issues"])
    want_tot = sum(len(r["want_laws"]) for r in rows)
    got_tot = sum(len(r["got_laws"]) for r in rows)
    verdicts = ("비조치", "조건부", "조치")
    conf = {(g, d): 0 for g in verdicts for d in verdicts + ("유보",)}
    hit = held = 0
    for r in rows:
        g = (labels.get(r["case_no"]) or {}).get("verdict")
        if g not in verdicts:
            continue
        d = r["verdict"] if r["verdict"] in verdicts else "유보"
        conf[(g, d)] += 1
        if d == "유보":
            held += 1
        elif d == g:
            hit += 1
    decided = n - held
    print(f"\n{'=' * 66}\nB트랙 사례 {n}건 · 평균 {sum(r['sec'] for r in rows) / n:.0f}초")
    print(f"  쟁점 발화   {fired}/{n} ({fired / n:.0%})")
    if want_tot:
        print(f"  법령 회수   {got_tot}/{want_tot} ({got_tot / want_tot:.0%})"
              f"   ※ 비조치의견서는 관련 법령을 머리에 밝힌다 — 상한")
    print(f"  판정 일치   {hit}/{decided} ({hit / max(decided, 1):.0%})   · 유보 {held}")
    print(f"\n혼동표 (행=정답 · 열=출력)   비조치  조건부   조치   유보   재현율")
    for g in verdicts:
        tot_g = sum(conf[(g, d)] for d in verdicts + ("유보",))
        rec = conf[(g, g)] / tot_g if tot_g else 0
        print(f"  정답 {g:<4}({tot_g:3}건)  "
              + "  ".join(f"{conf[(g, d)]:5}" for d in verdicts + ("유보",))
              + f"   {rec:.0%}")
    unc = [r["unclear"] for r in rows]
    print(f"\n  요건 판정 평균 {sum(r['subs'] for r in rows) / n:.0f} · 불명 평균 {sum(unc) / n:.0f}"
          f"  ← 포섭 기계가 제 트랙에서 내는 불명률")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    cs = cases()
    labels = json.loads(LABELS.read_text("utf-8")) if LABELS.is_file() else {}
    if args.report:
        rows = json.loads(LAST.read_text("utf-8"))["rows"] if LAST.is_file() else []
        score(rows, labels)
        return 0
    llm = _llm()
    if llm is None:
        print("LLM 없음 — ANTHROPIC_API_KEY 필요", file=sys.stderr)
        return 2
    if args.label:
        label(llm, cs, force=args.force)
        return 0
    picked = [c for c in cs if c["case_no"] == args.only] if args.only \
        else cs[:args.limit or 5]
    from lawrag.core.rag import index as index_mod
    idx = index_mod.current()
    rows = []
    print(f"B트랙 검토 {len(picked)}건 실행")
    for i, c in enumerate(picked, 1):
        try:
            r = run_one(llm, idx, c)
        except Exception as e:                       # 한 건이 죽어도 나머지는 돈다
            print(f"  !! {c['case_no']} 실패: {e}")
            continue
        rows.append(r)
        gold = (labels.get(c["case_no"]) or {}).get("verdict", "?")
        mark = "○" if r["verdict"] == gold else ("△" if r["verdict"] == "유보" else "✗")
        print(f"  [{i}/{len(picked)}] {mark} {c['case_no']} 쟁점{r['issues']} 요건{r['subs']}"
              f" → {r['verdict']} (정답 {gold}) {r['sec']}s")
    (args.out or LAST).write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1),
                                  "utf-8")
    score(rows, labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
