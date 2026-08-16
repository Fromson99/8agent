"""검토 골든 셋 — 정답이 붙은 사례로 오류율을 재고 **단계에 귀속**한다.

    python scripts/review_golden.py --label          # 회답 방향 라벨링 (1회, 캐시)
    python scripts/review_golden.py --limit 8        # 8건 실행 후 채점
    python scripts/review_golden.py --report         # 마지막 실행 재집계 (무비용)

법제처 해석례 67건은 그 자체로 **정답이 붙은 검토 사례**다 — 질의요지가
사실관계이고 회답이 정답이다. 이걸 검토 파이프라인에 통과시켜 회답과 대조하면
"오류가 많을 것 같은데"가 "오류가 몇 %이고 어디서 나는지 안다"로 바뀐다
(2026-08-14 사용자 결정: 다음은 기능이 아니라 자[尺]다).

## 무엇을 재나

    쟁점 발화   쟁점이 하나라도 섰나            → 2단계 실패 감지
    법령 회수   사례가 인용한 법령이 규범에 왔나 → 3단계 실패 감지 (결정론)
    방향 일치   결론 방향이 회답과 맞나          → 4단계 정확도

## 단계 귀속

틀린 사례를 넷 중 하나로 돌린다 — 어디를 고쳐야 하는지가 곧 답이다.

    쟁점 실패   쟁점이 0개 (검토가 시작도 못 함)
    회수 실패   쟁점은 섰으나 인용 법령을 하나도 못 데려옴
    포섭 실패   법령은 왔는데 방향이 틀림
    판단 유보   조건부·판단보류 — 오답이 아니라 회피 (별도로 센다)

## 읽을 때의 유의

질의요지는 대개 법령명을 이미 밝힌다("「자본시장과 금융투자업에 관한 법률」
제160조에 따르면…"). 실제 사용자 질문보다 **회수가 쉬운 셋**이라, 법령 회수율은
상한으로 읽어야 한다. 방향 일치율은 그 영향이 덜하다.

비용: 사례 하나에 LLM 콜 3~13회·30~60초다. 기본 상한을 작게 둔 이유다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

for _k, _v in (("STRUCTURE_STORE", "data/structure"),
               ("STRUCTURE_CUSTOM_DIR", "data/custom"),
               ("GLOSSARY_STORE", "data/glossary.json"),
               ("RAG_LINKS_STORE", "data/links.json")):
    os.environ.setdefault(_k, str(REPO_ROOT / _v))

INDEX = REPO_ROOT / "data" / "expc" / "index.json"
OUT_DIR = REPO_ROOT / "data" / "review"
LABELS = OUT_DIR / "golden_labels.json"
LAST = OUT_DIR / "golden_last.json"
TUNED = OUT_DIR / "golden_tuned_cases.json"     # 동결 — 이 밖의 사례가 홀드아웃
COLLOQ = OUT_DIR / "colloquial.json"            # 구어 변환 캐시 (1회 컴파일)

# 구어 변환 — 질의요지는 변호사 문체(법령·조문을 문면 인용)라 회수가 쉽다.
# 실사용 질문은 좌표 없이 상황만 말한다. 같은 사례·같은 정답에 문체만 바꿔
# 돌리면 "인용이 사라졌을 때 시스템이 얼마나 버티나"가 그대로 재진다.
COLLOQ_SYSTEM = (
    "너는 법제처 질의요지를 일반인의 구어 질문으로 바꾸는 변환기다.\n"
    "규칙: ① 법령명·조문 번호·'같은 법' 등 법률 좌표를 **전부 뺀다** — 일반인은 "
    "법을 모른 채 상황만 말한다. ② 사실관계(누가·무엇을·어떤 상황)는 더하지도 "
    "빼지도 않는다. ③ 1~3문장 존댓말 구어('~인가요?', '~해도 되나요?'). "
    "④ 각주 번호·정의 괄호 등 문서 장치는 버린다."
)
COLLOQ_SCHEMA = {"type": "object",
                 "properties": {"question": {"type": "string"}},
                 "required": ["question"], "additionalProperties": False}


def colloquial_of(llm, case: dict) -> str:
    """사례의 구어판 — 캐시가 정본, 없으면 LLM 으로 1회 컴파일."""
    have = json.loads(COLLOQ.read_text("utf-8")) if COLLOQ.is_file() else {}
    q = have.get(case["case_no"])
    if q:
        return q
    out = llm.structured("golden.colloquial", COLLOQ_SYSTEM,
                         f"[질의요지]\n{(case.get('issue') or '')[:2000]}",
                         COLLOQ_SCHEMA, max_tokens=400, effort="low")
    q = (out or {}).get("question") or (case.get("issue") or "")[:300]
    have[case["case_no"]] = q
    COLLOQ.write_text(json.dumps(have, ensure_ascii=False, indent=1), "utf-8")
    return q

LABEL_MODEL = "claude-opus-5"     # 자(尺)는 강한 모델로 — 하이쿠 라벨이 자를 흐렸다
# ── 방향의 정의 (2026-08-16 재정립) ─────────────────────────────────────────
# v1(하이쿠)·v2 초판(오푸스)이 서로 22% 어긋났고, 열어 보니 **"긍정"의 정의가
# 두 개**였다: ⑴ 회답 문장의 극성("할 수 있다"=긍정 / "아니다"=부정) ⑵ 물음
# 대비 답("…해야 하나요?"에 "아니다"면 부정, "…없어도 되나요?"에 "아니다"면 긍정).
# 21-0340 회답 "조정할 수 있습니다"가 부정으로, 20-0489 "규정이 있어야만 …
# 것은 아닙니다"(=없어도 된다)가 부정으로 라벨됐다 — 라벨러마다 축을 섞어 썼다.
# 시스템(interpret_case)은 회답처럼 문장을 내므로 채점 축은 **⑴ 회답 극성**이다.
# ⑵는 부가 필드(answer_to_question)로 따로 남긴다 — 나중에 쓰되 섞지 않는다.
LABEL_SYSTEM = (
    "너는 법제처 법령해석 회답의 **결론 문장 극성**을 뽑는 라벨러다 — 이 라벨이 "
    "시스템 채점의 자(尺)라 정확도가 전부다.\n"
    "**polarity(방향)는 회답 결론 문장 자체가 무엇을 말하는지**다 — 질문이 어떻게 "
    "물었는지와 무관하게:\n"
    "  긍정 = 결론이 '…할 수 있다 / …에 해당한다 / …포함된다 / …하여야 한다 / "
    "…필요하다 / …적용된다' 꼴. '~할 수 있습니다'는 긍정이다(가능성 판단의 "
    "법제처 문체).\n"
    "  부정 = 결론이 '…할 수 없다 / …에 해당하지 않는다 / …아니다 / …필요 없다 / "
    "…적용되지 않는다 / …것은 아니다' 꼴. 이중부정('…없어도 된다', '…있어야만 "
    "하는 것은 아니다')은 **부정 극성**이다 — 뜻이 허용이어도 문장 극성으로 판다.\n"
    "  조건부 = 회답이 '사정에 따라 결론이 갈린다 / …인 경우에는 …이고 …인 "
    "경우에는 …이다 / 종합 고려하여 판단'처럼 **결론을 갈라 둘 때만**.\n"
    "규율: ① 회답이 '가·나…'로 여러 물음에 답하면 물음마다 parts 에 따로 판정하고, "
    "polarity 는 첫 물음(주된 물음)을 따른다. ② evidence 는 결론 문장을 회답에서 "
    "**그대로** 옮긴다. ③ answer_to_question 은 별도 축이다: 질의요지의 물음에 "
    "대해 회답이 '예'인지 '아니오'인지 — 극성과 다를 수 있다('…없어도 되나요?'에 "
    "'…것은 아닙니다'면 극성 부정·물음 대비 예). ④ confidence: 결론 문장이 명시적이면 "
    "high, 문맥으로 읽어야 하면 medium, 결론이 흐리거나 극성 판정이 애매하면 low."
)
LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["긍정", "부정", "조건부"]},
        "answer_to_question": {"type": "string", "enum": ["예", "아니오", "갈림", "불명"]},
        "parts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "direction": {"type": "string", "enum": ["긍정", "부정", "조건부"]},
                "evidence": {"type": "string"}},
            "required": ["question", "direction", "evidence"],
            "additionalProperties": False}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["direction", "answer_to_question", "parts", "confidence"],
    "additionalProperties": False,
}
LABELS_V2 = OUT_DIR / "golden_labels_v2.json"    # 근거·확신도·물음별 — 사람 검증 대상 목록의 원천


def _llm():
    from core import llm as llm_mod
    llm_mod.load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return llm_mod.LLM()


def _cases() -> list:
    return json.loads(INDEX.read_text("utf-8"))["cases"]


# ---------------------------------------------------------------- 라벨링
def label(llm, cases: list, force: bool = False) -> dict:
    """회답 → 방향(+물음별·근거·확신도). 강한 모델로 매기고 캐시한다.

    v2 는 골든 자의 재보정이다(2026-08-16): 하이쿠가 매긴 v1 라벨은 사람 검증이
    없었고, "~할 수 있습니다"의 긍정/조건부 경계와 다부 회답(가·나)의 접힘이
    흐렸다. 자가 흐리면 시스템 오답과 라벨 오답을 못 가른다.
    """
    have = {} if force else (
        json.loads(LABELS_V2.read_text("utf-8")) if LABELS_V2.is_file() else {})
    todo = [c for c in cases if (force or c["case_no"] not in have)
            and (c.get("answer") or "")]
    print(f"라벨 v2 {len(have)}건 보유 · {len(todo)}건 새로 매긴다 ({LABEL_MODEL})")
    for i, c in enumerate(todo, 1):
        out = llm.structured("golden.label", LABEL_SYSTEM,
                             f"[질의요지]\n{(c.get('issue') or '')[:1500]}\n\n"
                             f"[회답]\n{c['answer'][:3000]}",
                             LABEL_SCHEMA, max_tokens=800, effort="medium",
                             model=LABEL_MODEL)
        if out:
            have[c["case_no"]] = out
        if i % 10 == 0:
            print(f"  … {i}/{len(todo)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_V2.write_text(json.dumps(have, ensure_ascii=False, indent=1), "utf-8")
    # 채점기가 읽는 얇은 표는 방향만 — v1 과 같은 모양이라 뒤가 안 바뀐다
    flat = {k: v["direction"] for k, v in have.items()}
    LABELS.write_text(json.dumps(flat, ensure_ascii=False, indent=1), "utf-8")
    low = [k for k, v in have.items() if v.get("confidence") == "low"]
    multi = [k for k, v in have.items() if len(v.get("parts") or []) > 1]
    print(f"라벨 {len(have)}건 저장 — {LABELS_V2.relative_to(REPO_ROOT)}")
    print(f"  사람 검증 대상(low) {len(low)}건: {' · '.join(low[:12])}")
    print(f"  다부 회답 {len(multi)}건: {' · '.join(multi[:12])}")
    return flat


# ---------------------------------------------------------------- 실행
def _direction(verdicts: list) -> str:
    """여러 쟁점의 결론을 하나로 — conclude() 와 같은 보수성."""
    cs = [v["conclusion"] for v in verdicts]
    if not cs:
        return "미정"
    if "불가" in cs:
        return "부정"
    if all(c == "가능" for c in cs):
        return "긍정"
    if all(c == "판단보류" for c in cs):
        return "미정"
    return "조건부"


import re

# 회답이 결론의 근거로 든 조문 — "「개인정보 보호법」 제35조제2항" 꼴.
# 법령명이 앞에 없으면 직전에 나온 법령명에 붙는다(회답 문체가 그렇다).
_LAW = re.compile(r"「([^」]+)」")
_JO = re.compile(r"(제\d+조(?:의\d+)?)")


def want_articles(case: dict) -> set:
    """회답에서 **결정적 조문**을 뽑는다 — 법령 수준 지표가 못 보는 실패를 잡는다.

    골든 25-0653 은 사례 인용 법령(개인정보 보호법)을 회수했으므로 법령 수준
    지표는 '성공'이었는데, 정작 필요한 제35조 대신 제15·17조를 가져왔다.
    조문 수준으로 재야 그 실패가 보인다.
    """
    text = case.get("answer") or ""
    out, law = set(), ""
    for m in re.finditer(r"「([^」]+)」|(제\d+조(?:의\d+)?)", text):
        if m.group(1):
            law = m.group(1).strip()
        elif law:
            out.add((law, m.group(2)))
    return out


def run_one(llm, idx, case: dict, text: Optional[str] = None) -> dict:
    """사례 하나를 검토에 통과시키고 채점에 필요한 것만 접는다.

    text 를 주면 질의요지 대신 그것으로 돈다(구어 골든) — 정답 라벨은 같다.
    """
    from core.casereview import pipeline as rp
    from core.rag import wikictx

    t0 = time.perf_counter()
    st = rp.run(llm, idx, (text or case.get("issue") or "")[:2000], track="해석")
    got_docs = {n.doc for n in st.norms}
    want = set(case.get("laws") or [])
    # 회수된 조문 좌표 — 규범의 경로에서 조를 읽는다 ("… ▸ 제35조")
    got_arts = set()
    for n in st.norms:
        for jo in _JO.findall(n.path or ""):
            got_arts.add((wikictx._pack(n.doc), jo))
    wa = {(wikictx._pack(l), j) for l, j in want_articles(case)}
    # 근거 정확도 — 판정이 basis 로 든 조문이 회답의 근거 조문과 겹치나.
    # 방향이 맞아도 근거가 엉뚱하면 실무에선 더 위험하다(그럴듯한 오답) — 이 자가
    # 없어서 그런 오답이 정답으로 세어지고 있었다. basis 는 "문서 ▸ 경로" 문자열이라
    # 문서명은 낫표 없이 앞머리, 조는 경로 어디든 "제N조" 로 잡는다.
    basis = (st.overall or {}).get("basis") or []
    got_basis = set()
    for b in basis:
        doc = wikictx._pack(str(b).split("▸")[0].strip())
        for jo in _JO.findall(str(b)):
            got_basis.add((doc, jo))
    return {"case_no": case["case_no"], "label": case.get("label", "")[:60],
            # 근거: 회답 근거 조문 중 시스템 basis 에 든 수 / 시스템이 든 basis 중
            # 회답 근거에 없는 수(과잉·엉뚱). 둘 다 (문서, 조) 단위.
            "basis_hit": len(wa & got_basis), "basis_n": len(got_basis),
            "basis_stray": len(got_basis - wa) if wa else 0,
            "issues": len(st.issues), "by_net": sum(1 for i in st.issues if i.by_net),
            "norms": len(st.norms), "subs": len(st.subs),
            "unclear": len(st.unresolved()),
            # 해석 판정(사안 수준)이 서면 그것이 방향이다 — 쟁점별 결론을
            # 다시 접으면 부수 쟁점의 유보가 본 쟁점의 판정을 희석한다.
            "direction": ({"긍정": "긍정", "부정": "부정", "조건부": "조건부"}
                          .get((st.overall or {}).get("direction"))
                          or _direction([{"conclusion": v.conclusion}
                                         for v in st.verdicts])),
            "interp": bool(st.overall),
            "want_laws": sorted(want), "got_laws": sorted(got_docs & want),
            "want_arts": len(wa), "got_arts": len(wa & got_arts),
            "sec": round(time.perf_counter() - t0, 1)}


# ---------------------------------------------------------------- 채점
def score(rows: list, labels: dict) -> None:
    n = len(rows)
    if not n:
        print("실행 결과가 없습니다 — --limit 로 먼저 돌리세요")
        return
    fired = sum(1 for r in rows if r["issues"])
    want_tot = sum(len(r["want_laws"]) for r in rows)
    got_tot = sum(len(r["got_laws"]) for r in rows)

    art_w = sum(r.get("want_arts", 0) for r in rows)
    art_g = sum(r.get("got_arts", 0) for r in rows)
    netted = sum(1 for r in rows if r.get("by_net"))

    hit = miss = held = unlabeled = 0
    blame = {"쟁점 실패": [], "회수 실패": [], "포섭 실패": []}
    held_blame = {"쟁점 실패": [], "회수 실패": [], "포섭 실패": []}

    def attribute(r: dict, bucket: dict) -> None:
        """어느 단계에서 났나 — 조문 수준까지 본다(법령만 보면 실패가 숨는다)."""
        if not r["issues"]:
            bucket["쟁점 실패"].append(r)
        elif r.get("want_arts") and not r.get("got_arts"):
            bucket["회수 실패"].append(r)          # 필요한 조문을 못 데려왔다
        elif r["want_laws"] and not r["got_laws"]:
            bucket["회수 실패"].append(r)
        else:
            bucket["포섭 실패"].append(r)

    for r in rows:
        gold = labels.get(r["case_no"])
        if gold is None:
            unlabeled += 1
            continue
        got = r["direction"]
        if got in ("미정", "조건부") and gold != "조건부":
            held += 1
            attribute(r, held_blame)               # 유보도 원인을 따진다
            continue
        if got == gold:
            hit += 1
            continue
        miss += 1
        attribute(r, blame)

    print(f"\n{'=' * 66}\n사례 {n}건 · 평균 {sum(r['sec'] for r in rows) / n:.0f}초")
    print(f"  쟁점 발화   {fired}/{n} ({fired / n:.0%})")
    if netted:
        print(f"  ※ 안전망이 세운 쟁점이 있는 사례 {netted}건 — 품질이 낮다")
    if want_tot:
        print(f"  법령 회수   {got_tot}/{want_tot} ({got_tot / want_tot:.0%})"
              f"   ※ 질의요지가 법령명을 밝히므로 상한으로 읽을 것")
    if art_w:
        print(f"  조문 회수   {art_g}/{art_w} ({art_g / art_w:.0%})"
              f"   ← 회답이 근거로 든 조문을 데려왔나 (법령 수준보다 엄격)")
    cmp_n = hit + miss
    if cmp_n:
        print(f"  방향 일치   {hit}/{cmp_n} ({hit / cmp_n:.0%})"
              f"   · 판단 유보 {held} · 미라벨 {unlabeled}")
    # 근거 정확도 — 방향과 별개의 축. "방향 맞고 근거도 맞음"이 진짜 정답이다.
    with_basis = [r for r in rows if r.get("basis_n")]
    if with_basis:
        b_hit = sum(r["basis_hit"] for r in with_basis)
        b_want = sum(r.get("want_arts", 0) for r in with_basis)
        b_stray = sum(r.get("basis_stray", 0) for r in with_basis)
        b_n = sum(r["basis_n"] for r in with_basis)
        both = sum(1 for r in with_basis
                   if labels.get(r["case_no"]) == r["direction"] and r["basis_hit"])
        dir_ok = sum(1 for r in with_basis if labels.get(r["case_no"]) == r["direction"])
        print(f"  근거 회수   {b_hit}/{b_want} ({b_hit / max(b_want, 1):.0%})"
              f"   ← 회답 근거 조문이 시스템 basis 에 들었나 (조 단위)")
        print(f"  근거 과잉   {b_stray}/{b_n} ({b_stray / max(b_n, 1):.0%})"
              f"   ← 시스템 basis 중 회답에 없는 조문 (엉뚱한 근거의 비율)")
        print(f"  방향+근거   {both}/{dir_ok}   ← 방향 맞은 것 중 근거도 맞은 것 — 이게 진짜 정답")
    else:
        print(f"  방향 일치   비교 가능 0건 · 판단 유보 {held} · 미라벨 {unlabeled}")

    # 혼동표 — 방향 일치율만 보면 편향을 못 잡는다. 홀드아웃 실측(2026-08-16):
    # 일치 47%인데 정답 긍정 52건 중 긍정 출력이 4건(8%), 27건을 부정으로
    # 뒤집었다 — 출력 분포가 정답 분포와 거꾸로였다. 이 표가 없어서 4회차까지
    # 그 편향을 못 봤다.
    dirs = ("긍정", "부정", "조건부")
    conf = {(g, d): 0 for g in dirs for d in dirs + ("미정",)}
    for r in rows:
        g = labels.get(r["case_no"])
        if g in dirs:
            conf[(g, r["direction"] if r["direction"] in dirs else "미정")] += 1
    print(f"\n혼동표 (행=정답 · 열=출력)      긍정   부정  조건부   미정   재현율")
    for g in dirs:
        tot_g = sum(conf[(g, d)] for d in dirs + ("미정",))
        rec = conf[(g, g)] / tot_g if tot_g else 0
        print(f"  정답 {g:<4}({tot_g:3}건)   "
              + "  ".join(f"{conf[(g, d)]:5}" for d in dirs + ("미정",))
              + f"   {rec:.0%}")
    out_dist = {d: sum(conf[(g, d)] for g in dirs) for d in dirs}
    gold_dist = {g: sum(conf[(g, d)] for d in dirs + ("미정",)) for g in dirs}
    skew = {d: (out_dist[d] / max(gold_dist[d], 1)) for d in dirs}
    print(f"  출력/정답 비율 — " + " · ".join(f"{d} {skew[d]:.2f}" for d in dirs)
          + "   (1.0 = 분포 일치 · 크면 그쪽으로 남발)")

    if miss:
        print(f"\n단계 귀속 — 틀린 {miss}건이 어디서 났나")
        for k, v in blame.items():
            if v:
                print(f"  {k:<8} {len(v)}건 — "
                      + " · ".join(r["case_no"] for r in v[:6]))
    if held:
        print(f"\n판단 유보 {held}건 — 오답이 아니라 회피다. 원인 귀속:")
        for k, v in held_blame.items():
            if v:
                print(f"  {k:<8} {len(v)}건 — "
                      + " · ".join(r["case_no"] for r in v[:6]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", action="store_true", help="회답 방향 라벨링(v2 · 강한 모델)")
    ap.add_argument("--force", action="store_true", help="--label 과 함께: 캐시 무시하고 전부 다시")
    ap.add_argument("--limit", type=int, default=0, help="실행할 사례 수")
    ap.add_argument("--only", help="특정 안건번호만 (예: 25-0484)")
    ap.add_argument("--report", action="store_true", help="마지막 실행 재집계")
    ap.add_argument("--holdout", action="store_true",
                    help="동결 목록(golden_tuned_cases.json) 밖 사례만 — 튜닝에 안 쓴 검증 셋")
    ap.add_argument("--out", type=Path, default=None,
                    help="결과 저장 경로 (기본 golden_last.json) — 실행 판을 잃지 않기 위해")
    ap.add_argument("--colloquial", action="store_true",
                    help="질의요지 대신 구어 변환(법령명·조번호 제거)으로 돌린다 — 문체 강건성 측정")
    args = ap.parse_args()

    if not INDEX.is_file():
        print("색인이 없습니다 — ingest_expc.py 먼저", file=sys.stderr)
        return 2
    cases = _cases()
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
        label(llm, cases, force=args.force)
        return 0

    if args.only:
        picked = [c for c in cases if c["case_no"] == args.only]
    elif args.holdout:
        tuned = set(json.loads(TUNED.read_text("utf-8"))["case_nos"]) \
            if TUNED.is_file() else set()
        picked = [c for c in cases if c["case_no"] not in tuned
                  and (c.get("answer") or "")][:args.limit or 10**9]
        print(f"홀드아웃 — 동결 {len(tuned)}건 밖 {len(picked)}건 (튜닝 금지 셋)")
    else:
        picked = cases[:args.limit or 5]
    if not picked:
        print("고른 사례가 없습니다", file=sys.stderr)
        return 2

    from core.rag import index as index_mod
    idx = index_mod.current()
    rows = []
    print(f"검토 {len(picked)}건 실행 — 사례당 30~60초")
    for i, c in enumerate(picked, 1):
        try:
            txt = colloquial_of(llm, c) if args.colloquial else None
            r = run_one(llm, idx, c, text=txt)
        except Exception as e:                       # 한 건이 죽어도 나머지는 돈다
            print(f"  !! {c['case_no']} 실패: {e}")
            continue
        rows.append(r)
        gold = labels.get(r["case_no"], "?")
        mark = "○" if r["direction"] == gold else (
            "△" if r["direction"] in ("미정", "조건부") else "✗")
        print(f"  [{i}/{len(picked)}] {mark} {r['case_no']} "
              f"쟁점{r['issues']} 요건{r['subs']} → {r['direction']} (정답 {gold})"
              f" {r['sec']}s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.out or LAST
    out_path.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1),
                        "utf-8")
    score(rows, labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
