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

## 읽을 때의 유의 — A/B 두 종류의 질문

질의요지는 대개 법령명·조를 이미 밝힌다("「자본시장과 금융투자업에 관한 법률」
제160조에 따르면…"). 회수는 그 인용을 **좌표로 펴서**(pipeline._cite_coords)
답 조문을 데려오므로 이런 질문은 검색 실력을 재지 않는다. 그래서 질문을 둘로 가른다:

    A  문면에 「법령」제N조 인용이 있음  — 회수 = 주소 펴기 (쉬움 · 상한)
    B  인용이 없음                        — 회수 = 쟁점 문장·벡터로 찾기 (실사용에 가까움)

실측(2026-08-17): 질의요지 원문 180건은 A 136 / B 44 (76%가 A) — 실사용과
반대다. `--mix 20:80` 은 재료 있는 사례를 A(질의요지 그대로)·B(구어 변환 —
법령명·조 번호 제거)로 2:8 배분해 돌리고 A/B 별로 따로 접는다. B 의 점수가
이 시스템의 실사용 실력이다.

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
    from lawrag.core import llm as llm_mod
    llm_mod.load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return llm_mod.LLM()


def is_ipa(case: dict) -> bool:
    """정보공개법 사례인가 — 셋에서 뺄 수 있게 표시한다.

    창고에 「공공기관의 정보공개에 관한 법률 **시행령**」이 없고, 이 계열 사례는
    거의 전부 시행령 제2조 각 호("특별법에 따라 설립된 특수법인")가 결정 마디다.
    즉 이 무리는 회수 결함이 아니라 수집 공백으로 통째로 실패한다 — 섞어 재면
    회수 점수만 낮아지고 진짜 문제가 가려진다 (docs/RETRIEVAL.md 2장).
    시행령을 수집하지 않기로 했으므로 셋에서 뺀다.
    """
    txt = (case.get("issue") or "") + (case.get("answer") or "") + str(case.get("laws") or "")
    return "정보공개" in txt


def _cases(drop_ipa: bool = False) -> list:
    cases = json.loads(INDEX.read_text("utf-8"))["cases"]
    if drop_ipa:
        cases = [c for c in cases if not is_ipa(c)]
    return cases


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


# 대조 어구 — "「민법」 또는 「상법」 **외에** 다른 개별법" 처럼 *아닌 것*을 말하려고
# 든 법령명은 정답이 아니다. 08-0204 에서 이유의 이 어구 때문에 「상법」이 정답
# 법령으로 들어가, 실재 법령을 다 맞힌 시스템이 2/3 로 깎였다 (docs/RETRIEVAL.md 1-7).
_CONTRAST = re.compile(r"(?:외에|외의|이 아니라|가 아니라|과 달리|와 달리|아닌)")
# "같은 법 시행령/시행규칙" — 앞선 「법령」에 붙는 하위 법령. 낫표가 없어 정규식이
# 못 보고 본법으로 붙였다. 골든 180건 중 21건이 걸린다 (docs/RETRIEVAL.md 1-1).
_SAME = re.compile(r"(같은|동)\s*법(?:\s*(시행령|시행규칙|시행세칙))?")


def want_articles(case: dict) -> set:
    """회답·이유에서 **결정적 조문**을 뽑는다 — 법령 수준 지표가 못 보는 실패를 잡는다.

    골든 25-0653 은 사례 인용 법령(개인정보 보호법)을 회수했으므로 법령 수준
    지표는 '성공'이었는데, 정작 필요한 제35조 대신 제15·17조를 가져왔다.
    조문 수준으로 재야 그 실패가 보인다.

    **자를 열어보고 고친 것 셋** (2026-08-17, 10건 마킹 — docs/RETRIEVAL.md 1장):

    ① `reason` 까지 읽는다. 회답은 결론 한두 문장이고 실질 논증은 이유에 있다.
       07-0319 의 결정 마디 4개는 전부 이유에만 나왔다.
    ② "같은 법 시행령" 을 하위 법령으로 푼다. 13-0423 은 "「정보공개법」제13조제1항
       및 **같은 법 시행령** 제14조제2항" 인데 시행령이 사라져 본법 제14조('부분
       공개' — 물음과 무관)가 정답으로 들어갔다.
    ③ 대조 어구에서 긁지 않는다 (_CONTRAST).

    여전히 못 하는 것: 지시 표현("동호"·"라목")을 못 읽어 **조(條) 단위**에 머문다.
    항·호 단위 정본은 사람·에이전트 마킹으로 따로 만든다.
    """
    # `reason` 은 읽지 않는다 — 한 번 넣어 봤다가 뺐다 (2026-08-17).
    # 결정 마디가 이유에만 있는 것은 사실이라 재현율은 31%→71% 로 올랐는데,
    # 이유는 전제·배경도 잔뜩 인용해 정밀도가 85%→32% 로 무너졌다(F1 46%→44%,
    # 창고 보유분만 보면 65%→28%). 결정과 배경을 정규식으로는 못 가른다 —
    # 그 일은 마킹(data/review/marked_*.json)이 한다.
    parts = [case.get("answer") or ""]
    out: set = set()
    for text in parts:
        law, base = "", ""
        for m in re.finditer(r"「([^」]+)」|(제\d+조(?:의\d+)?)|(같은\s*법(?:\s*시행령|\s*시행규칙|\s*시행세칙)?|동\s*법)", text):
            if m.group(1):                          # 「법령명」
                law = m.group(1).strip()
                base = law                          # 뒤따르는 "같은 법" 의 기준
                # 대조 어구 뒤에 온 법령명은 "아닌 것" 이다 — 정답에서 뺀다
                tail = text[m.end():m.end() + 12]
                if _CONTRAST.search(tail):
                    law = ""
            elif m.group(3):                        # "같은 법 시행령" 류
                if not base:
                    continue
                sub = _SAME.match(m.group(3).strip())
                kind = sub.group(2) if sub else None
                law = f"{base} {kind}" if kind else base
            elif law:                               # 제N조
                # **바로 앞** 12자에 "부칙" 이 있을 때만 부칙의 조다 — got 쪽과 표시를
                # 맞춘다. 창을 넓게 잡으면 "부칙 제5조에 따라 제28조는…" 에서 뒤의
                # 제28조(본칙)까지 부칙으로 번진다. 사이에 낀 「법령」·조 표기도 끊는다.
                head = text[max(0, m.start() - 12):m.start()]
                pre = "부칙 " if "부칙" in head and "조" not in head.split("부칙")[-1] else ""
                out.add((law, pre + m.group(2)))
    return out


def material_status(idx, case: dict) -> tuple:
    """(상태, 회답 근거 조문 수, 창고에 있는 수). 상태 = 전부 | 일부 | 전무 | 근거없음.

    "못 찾았다"에는 두 가지가 섞여 있다 — 창고에 있는데 못 찾은 것(회수 결함)과
    창고에 없는 것(수집 공백). 섞어 재면 회수 점수가 늘 낮아 판정 문제가 가려진다.
    실측(2026-08-16 홀드아웃): 회답 근거 조문 145개 중 52%가 창고에 없는 법령이었고,
    창고에 전부 있는 25건은 조문 회수 90%였다 — 회수는 멀쩡, 재료가 없었다.
    """
    from lawrag.core.rag import wikictx
    wa = want_articles(case)
    if not wa:
        return ("근거없음", 0, 0)
    by_law = {wikictx._pack(v.name): v for v in idx.docs.values()}
    have = 0
    for law, jo in wa:
        v = by_law.get(wikictx._pack(law))
        if v is None:
            continue
        for n in v.by_id:
            p = v.path(n) or ""
            if "부칙" in p:
                continue
            if any(seg == jo or seg.startswith(jo + " ") for seg in p.split(" ▸ ")):
                have += 1
                break
    st = "전부" if have == len(wa) else ("전무" if have == 0 else "일부")
    return (st, len(wa), have)


MARKED = OUT_DIR / "marked.json"
_HANJO = re.compile(r"[①-⑳]|^\d+\.$|^[가-힣]\.$")


def marked() -> dict:
    """골든 v2 정본 — 원문을 열어 **항·호까지** 짚은 정답 (data/review/marked.json).

    옛 자(want_articles)는 회답을 정규식으로 긁는다. 그 자의 결함이 원문 마킹
    38건에서 드러났다(docs/RETRIEVAL.md 1장) — 전제 인용을 정답으로 세고,
    조(條) 단위라 제9조 아래 20개 마디 중 아무거나 맞혀도 만점이며, 부칙을
    본칙과 뭉갠다. 13-0365 는 **정답이 부칙**인데 옛 자는 본칙 제28조를
    정답이라 불렀다.

    정본이 있는 사례는 이것을 쓰고, 없으면 옛 자로 물러난다.
    """
    if not MARKED.is_file():
        return {}
    return json.loads(MARKED.read_text("utf-8")).get("cases", {})


def _node_of(idx, law: str, node_id: str):
    """(법령명, node_id) → (DocView, 마디). 못 찾으면 (None, None)."""
    from lawrag.core.rag import wikictx
    key = wikictx._pack(law)
    for v in idx.docs.values():
        if wikictx._pack(v.name) == key:
            n = v.by_id.get(node_id) or v.by_id.get(str(node_id))
            try:
                n = n or v.by_id.get(int(node_id))
            except (TypeError, ValueError):
                pass
            return (v, n) if n is not None else (v, None)
    return (None, None)


def _ancestors(v, node_id) -> set:
    """그 마디와 조상 전부의 id — 회수가 조 단위여도 항·호를 담았는지 본다."""
    out, cur, seen = set(), node_id, set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        out.add(str(cur))
        n = v.by_id.get(cur)
        if n is None:
            break
        cur = n.get("parent")
    return out


def score_marked(case_no: str, st, idx) -> Optional[dict]:
    """골든 v2 정본으로 한 사례를 잰다 — **회수와 근거를 다른 잣대로** 본다.

    회수(retrieval)  정답 마디가 회수한 구역 **안에** 들어왔나 (조상 포함).
                     조 단위로 제9조를 데려왔어도 라목 텍스트는 실제로 들어왔다.
                     "그 글자를 봤나"를 묻는 것이므로 포함이 맞다.
    근거(basis)      판정이 **그 항·호를 짚었나** (좌표 일치).
                     06-0131 의 답은 제9조제1항제6호 라목 하나인데 제9조 아래
                     마디가 20개다 — 조 단위로는 아무거나 맞혀도 만점이라
                     여기서만 진짜 정밀도가 드러난다.

    둘을 나눠야 "회수는 됐는데 판정이 엉뚱한 데를 짚었다"가 보인다.
    """
    m = marked().get(case_no)
    if not m or not m.get("decisive_full"):
        return None
    from lawrag.core.rag import wikictx

    got_nodes = set()                       # 회수한 구역과 그 하위 전부
    # 정의 칸(state.glossary)도 회수로 센다 — 규범 상한 밖의 별도 칸이지만
    # 판정 프롬프트에 실리므로 "그 글자를 봤다"는 사실은 같다.
    for n in list(st.norms) + [
            type("G", (), {"doc_id": g.doc_id, "node": g.node})()
            for g in getattr(st, "glossary", [])]:
        v = idx.docs.get(n.doc_id)
        if v is None:
            continue
        stack = [n.node]
        while stack:
            cur = stack.pop()
            got_nodes.add((wikictx._pack(v.name), str(cur)))
            stack.extend(k["id"] for k in v.nodes if k.get("parent") == cur)

    # st.overall 은 dict 다 (판정 콜의 파싱 결과) — 객체가 아니다
    basis_txt = " ".join(str(b) for b in ((st.overall or {}).get("basis") or []))
    ret_hit = base_hit = 0
    detail = []
    for d in m["decisive_full"]:
        law, nid = d.get("law", ""), str(d.get("node_id", ""))
        v, node = _node_of(idx, law, nid)
        key = wikictx._pack(law)
        r = (key, nid) in got_nodes
        # 근거 — 판정이 그 좌표를 짚었나. 마디의 경로에서 조·항·호를 뽑아 대조한다.
        b = False
        if v is not None and node is not None:
            path = v.path(node["id"]) or ""
            segs = [x.strip() for x in path.split(" ▸ ")]
            jo = next((x.split(" ")[0] for x in segs if re.match(r"^제\d+조", x)), "")
            leaf = (node.get("surface") or "").strip(" .")
            flat = re.sub(r"\s|「|」", "", basis_txt)
            if jo and jo.replace(" ", "") in flat:
                # 조까지 맞았으면 잎(항·호·목)까지 짚었는지 본다
                num = re.sub(r"[^\d가-힣]", "", leaf)
                b = (not num) or any(num + t in flat for t in ("호", "목", "항", "")) \
                    or leaf in basis_txt
        ret_hit += bool(r)
        base_hit += bool(b)
        detail.append({"law": law, "node_id": nid,
                       "jo": d.get("jo"), "hang_ho": d.get("hang_ho"),
                       "retrieved": bool(r), "cited": bool(b)})
    n = len(m["decisive_full"])
    return {"n_decisive": n, "ret_hit": ret_hit, "basis_hit": base_hit,
            "direction_gold": m.get("direction"), "detail": detail}


def _basis_coords(b: str) -> set:
    """판정의 basis 문자열 하나 → {(문서명(공백 제거·낫표 제거), 제N조)}.

    "「개인정보 보호법」 제17조제1항 · 같은 법 시행령 제14조" 처럼 한 문자열에
    여러 조가 오면 각각 잡되 문서는 그 조 앞의 마지막 문서명이다.
    """
    from lawrag.core.rag import wikictx
    s = b.replace("▸", " ").replace("「", " ").replace("」", " ")
    out, doc, last = set(), "", 0
    for m in _JO.finditer(s):
        head = s[last:m.start()]
        # 마지막 조각(· , ; 로 나뉜)만 문서명 후보다. 편·장·절 제목과 <개정 …> 은 떼고,
        # 문서명은 법·법률·령·규정·규칙·세칙·고시·조례로 끝나는 조각만 인정한다.
        frags = [f.strip(" ·,;:") for f in re.split(r"[·,;]", head)]
        frags = [f for f in frags if f]
        cand = frags[-1] if frags else ""
        cand = re.sub(r"제\d+[편장절관].*$|<.*$|제\d+항.*$|제\d+호.*$", "", cand).strip(" ·,;:")
        if cand and re.search(r"(법|법률|령|규정|규칙|세칙|고시|조례)$", cand) \
                and "같은" not in cand and "동법" not in cand:
            doc = cand
        elif cand and "시행령" in cand and doc and "시행령" not in doc:
            doc = doc + " 시행령"
        if doc:
            out.add((wikictx._pack(doc), m.group(1)))
        last = m.end()
    return out


def question_mode(idx, text: str) -> str:
    """질문의 종류 — A(문면에 「법령」제N조 인용 → 좌표로 펴진다) / B(없음 → 검색)."""
    from lawrag.core.casereview import pipeline as rp
    return "A" if rp._cite_coords(idx, text or "") else "B"


def run_one(llm, idx, case: dict, text: Optional[str] = None) -> dict:
    """사례 하나를 검토에 통과시키고 채점에 필요한 것만 접는다.

    text 를 주면 질의요지 대신 그것으로 돈다(구어 골든) — 정답 라벨은 같다.
    """
    from lawrag.core.casereview import pipeline as rp
    from lawrag.core.rag import wikictx

    t0 = time.perf_counter()
    log_start = len(getattr(llm, "log", []))
    q_text = (text or case.get("issue") or "")[:2000]
    st = rp.run(llm, idx, q_text, track="해석")
    got_docs = {n.doc for n in st.norms}
    want = set(case.get("laws") or [])
    # 회수된 조문 좌표 — 규범의 경로에서 조를 읽는다 ("… ▸ 제35조")
    got_arts = set()
    for n in st.norms:
        # 부칙은 본칙과 **다른 규범**이지만 **버릴 것도 아니다**. 둘 다 겪었다:
        #  · 정보공개법의 `제2조` 는 넷(본칙 정의 · 부칙 경과조치 · 적용례 · 개정
        #    경과조치)이라, 표면만 비교하면 부칙을 집어와도 적중으로 세어졌다.
        #  · 그렇다고 부칙을 빼면 13-0365 가 죽는다 — 그 사건의 **정답이 부칙**이다
        #    (개정법 적용례. 본칙 제28조만 맞히면 0점이어야 한다).
        # 그래서 배제가 아니라 **표시**한다. 회답도 "부칙 제5조" 라고 쓰므로
        # want 쪽(want_articles)도 같은 표시를 달아 짝이 맞는다.
        # 골든 180건 중 회답·이유가 부칙을 말하는 사례는 16건. (docs/RETRIEVAL.md 1-5)
        pre = "부칙 " if "부칙" in (n.path or "") else ""
        for jo in _JO.findall(n.path or ""):
            got_arts.add((wikictx._pack(n.doc), pre + jo))
    wa = {(wikictx._pack(l), j) for l, j in want_articles(case)}
    # 근거 정확도 — 판정이 basis 로 든 조문이 회답의 근거 조문과 겹치나.
    # 방향이 맞아도 근거가 엉뚱하면 실무에선 더 위험하다(그럴듯한 오답) — 이 자가
    # 없어서 그런 오답이 정답으로 세어지고 있었다. basis 는 판정 모델이 쓰는 문자열이라
    # 형식이 둘이다 — "문서 ▸ 제9조 ▸ ①" 또는 "공공기관의 정보공개에 관한 법률
    # 제9조제1항제5호"(▸ 없음). 문서명은 **첫 "제N조" 앞까지**로 잡는다 — 홀드아웃
    # v3 에서 basis 217개 중 적중 0 은 ▸ 로만 잘라 조 번호까지 문서명에 붙었던
    # 자 버그였다(2026-08-17 실측). 조는 문자열 어디든 "제N조" 로 잡는다.
    basis = (st.overall or {}).get("basis") or []
    got_basis = set()
    for b in basis:
        got_basis |= _basis_coords(str(b))
    mat, mat_n, mat_have = material_status(idx, case)
    row = {"case_no": case["case_no"], "label": case.get("label", "")[:60],
            "facts": len(st.facts),
            # 질문 종류 — 실제로 돌린 문장 기준 (구어 변환이면 대개 B)
            "mode": question_mode(idx, q_text), "text_kind": "구어" if text else "질의요지",
            "material": mat, "material_have": f"{mat_have}/{mat_n}",
            # 근거: 회답 근거 조문 중 시스템 basis 에 든 수 / 시스템이 든 basis 중
            # 회답 근거에 없는 수(과잉·엉뚱). 둘 다 (문서, 조) 단위.
            "basis_hit": len(wa & got_basis), "basis_n": len(got_basis),
            "basis_stray": len(got_basis - wa) if wa else 0,
            "basis_raw": [str(b)[:120] for b in basis][:12],   # 자를 다시 만들 때 재채점용
            "want_arts_list": sorted(f"{l} {j}" for l, j in want_articles(case)),
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
    # 골든 v2 정본이 있으면 **항·호 단위**로 한 번 더 잰다 (docs/RETRIEVAL.md).
    # 옛 지표(want_arts/got_arts)는 조 단위라 남겨 둔다 — 두 자를 나란히 봐야
    # 새 자가 얼마나 엄격해졌는지가 보인다.
    mk = score_marked(case["case_no"], st, idx)
    if mk:
        row["m_n"] = mk["n_decisive"]
        row["m_ret"] = mk["ret_hit"]           # 정답 마디가 회수 구역에 들어왔나
        row["m_basis"] = mk["basis_hit"]       # 판정이 그 항·호를 짚었나
        row["m_gold"] = mk["direction_gold"]
        row["m_detail"] = mk["detail"]
    exchanges = list(getattr(llm, "log", []))[log_start:]
    truncated = [x for x in exchanges
                 if getattr(x, "stop_reason", "") == "max_tokens"
                 or ("max_tokens" in str(getattr(x, "error", ""))
                     and "잘림" in str(getattr(x, "error", "")))]
    row["usage"] = {
        "calls": len(exchanges),
        "input_tokens": sum(int((x.usage or {}).get("input_tokens", 0))
                            for x in exchanges),
        "output_tokens": sum(int((x.usage or {}).get("output_tokens", 0))
                             for x in exchanges),
        "duration_ms": sum(int(x.dur_ms) for x in exchanges),
        "ttft_ms": max((int(x.ttft_ms) for x in exchanges), default=0),
        "errors": sum(bool(x.error) for x in exchanges),
        "truncated_calls": len(truncated),
    }
    norm_chars = sum(len(getattr(req, "text", "") or "")
                     for norm in st.norms for req in norm.reqs)
    glossary_chars = sum(len(getattr(norm, "text", "") or "")
                         for norm in getattr(st, "glossary", []))
    try:
        from lawrag.core.rag import lexicon as lexicon_mod
        lexicon_stats = dict(lexicon_mod.current(idx).cache_stats)
    except Exception:
        lexicon_stats = {}
    row["runtime"] = {
        "final_contexts": len(st.norms) + len(getattr(st, "glossary", [])),
        "context_chars": norm_chars + glossary_chars,
        "truncated_sections": len(truncated), "shared_cap_overflow": False,
        "truncation_stages": [str(x.kind) for x in truncated],
        "channel_counts": {},
        "stage_counts": {
            "fact_extraction": len(st.facts), "issue_spot": len(st.issues),
            "norm_retrieval": len(st.norms), "subsumption": len(st.subs),
            "final_decision": int(bool(st.overall)),
        },
        "lexicon_cache_terms": int(lexicon_stats.get("terms", 0)),
        "lexicon_cache_missing": int(lexicon_stats.get("missing", 0)),
        "lexicon_cache_coverage": float(lexicon_stats.get("coverage", 0.0)),
        "lexicon_runtime_compiled": bool(lexicon_stats.get("compiled", False)),
    }
    return row


# ---------------------------------------------------------------- 채점
def verdict(gold, got: str) -> str:
    """정답·출력 한 쌍 → 적중 / 오답 / 유보 / 미라벨. **자는 하나여야 한다.**

    이 규칙이 score() 안에 세 번 따로 적혀 있었고 셋이 서로 달랐다 — A/B 블록만
    "출력이 조건부면 무조건 제외"라, 정답이 조건부인 사례를 맞혀도(06-0128) 유보로
    떨어뜨려 A트랙을 1건씩 과소 보고했다(혼합 골든 v1·v2·v3 셋 다). 여기 한 곳만
    고치면 세 곳이 같이 움직인다.

    유보의 뜻은 "답을 안 냈다"이다: 미정은 언제나 회피이고, 조건부는 정답이
    조건부가 아닐 때만 회피다(정답이 조건부면 그게 곧 답이다).
    """
    if gold not in ("긍정", "부정", "조건부"):
        return "미라벨"
    if got == "미정" or (got == "조건부" and gold != "조건부"):
        return "유보"
    return "적중" if got == gold else "오답"


def tally(rows: list, labels: dict) -> tuple:
    """행 묶음 → (적중, 오답, 유보, 미라벨). verdict() 하나만 본다."""
    c = {"적중": 0, "오답": 0, "유보": 0, "미라벨": 0}
    for r in rows:
        c[verdict(labels.get(r["case_no"]), r["direction"])] += 1
    return c["적중"], c["오답"], c["유보"], c["미라벨"]


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
        v = verdict(labels.get(r["case_no"]), r["direction"])
        if v == "미라벨":
            unlabeled += 1
        elif v == "유보":
            held += 1
            attribute(r, held_blame)               # 유보도 원인을 따진다
        elif v == "적중":
            hit += 1
        else:
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
    # 재료 상태별 — 창고에 재료가 다 있는 사례에서만 회수·판정 실력이 온전히 보인다.
    by_mat: dict = {}
    for r in rows:
        by_mat.setdefault(r.get("material", "?"), []).append(r)
    if len(by_mat) > 1:
        print(f"\n재료 상태별 (회답 근거 조문이 창고에…)")
        for k in ("전부", "일부", "전무", "근거없음"):
            rs = by_mat.get(k)
            if not rs:
                continue
            h, ms, hd, _ = tally(rs, labels)
            a = sum(r.get("got_arts", 0) for r in rs); w = sum(r.get("want_arts", 0) for r in rs)
            print(f"  {k:5} {len(rs):3}건   방향 {h}/{h + ms} ({h / max(h + ms, 1):.0%})"
                  f" 유보 {hd}"
                  + (f"   조문 회수 {a}/{w} ({a / w:.0%})" if w else ""))
    # A/B — 문면 인용이 있는 질문(A: 회수 = 주소 펴기)과 없는 질문(B: 회수 = 검색).
    # 같은 사례·같은 정답이라도 B 가 이 시스템의 실사용 실력이다 (모듈 머리 §A/B).
    by_mode: dict = {}
    for r in rows:
        by_mode.setdefault(r.get("mode", "?"), []).append(r)
    if len(by_mode) > 1 or "B" in by_mode:
        print(f"\n질문 종류별 (A 문면 인용 있음=주소 펴기 · B 없음=검색)")
        for k in ("A", "B"):
            rs = by_mode.get(k)
            if not rs:
                continue
            h, ms, hd, _ = tally(rs, labels)
            a = sum(r.get("got_arts", 0) for r in rs); w = sum(r.get("want_arts", 0) for r in rs)
            bh = sum(r.get("basis_hit", 0) for r in rs); bw = sum(r.get("want_arts", 0) for r in rs if r.get("basis_n"))
            both = sum(1 for r in rs if labels.get(r["case_no"]) == r["direction"] and r.get("basis_hit"))
            print(f"  {k} {len(rs):3}건   조문 회수 {a}/{w} ({a / max(w, 1):.0%})"
                  f"   방향 {h}/{h + ms} ({h / max(h + ms, 1):.0%}) 유보 {hd}"
                  f"   근거 회수 {bh}/{bw} ({bh / max(bw, 1):.0%})   방향+근거 {both}")

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
        # 근거 칸이 없는 옛 결과 파일 — "방향 일치"를 다시 찍지 않는다(위에서 이미
        # 찍었다). 같은 이름을 두 뜻으로 쓰던 자리다(9-3 과 같은 부류).
        print("  근거 지표   없음 — basis 를 저장하지 않던 때의 결과 파일이다")

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
    ap.add_argument("--golden2", action="store_true",
                    help="골든 v2 — data/review/marked.json 에 항·호 정본이 있는 사례만. "
                         "재료 필터를 타지 않는다(그 필터가 옛 자 위에 서 있어 "
                         "조번호가 개정으로 밀린 사례를 떨군다 — docs/RETRIEVAL.md)")
    ap.add_argument("--no-ipa", action="store_true",
                    help="정보공개법 사례를 뺀다 — 시행령이 창고에 없어 이 무리는 "
                         "수집 공백으로 통째로 실패한다 (docs/RETRIEVAL.md 2장)")
    ap.add_argument("--cases", default="",
                    help="안건번호 여러 개를 쉼표로 (예: 07-0338,18-0124). --mix 와 "
                         "같이 쓰면 **배분을 51건 전체로 계산한 뒤** 이 목록만 남긴다 "
                         "— 그래서 전체 판과 A/B·질문지가 정확히 같다(빠른 되먹임용).")
    ap.add_argument("--suite", type=Path,
                    help="고정 E2E 사건판 JSON(case_nos, mix)을 실행 — 사건 문자열을 "
                         "명령마다 복사하지 않아 같은 판을 재현한다")
    ap.add_argument("--report", action="store_true", help="마지막 실행 재집계")
    ap.add_argument("--holdout", action="store_true",
                    help="동결 목록(golden_tuned_cases.json) 밖 사례만 — 튜닝에 안 쓴 검증 셋")
    ap.add_argument("--material", action="store_true",
                    help="회답 근거 조문이 창고에 전부 있는 사례만 — 회수·판정 실력을 재료 공백과 분리해 잰다")
    ap.add_argument("--out", type=Path, default=None,
                    help="결과 저장 경로 (기본 golden_last.json) — 실행 판을 잃지 않기 위해")
    ap.add_argument("--colloquial", action="store_true",
                    help="질의요지 대신 구어 변환(법령명·조번호 제거)으로 돌린다 — 문체 강건성 측정")
    ap.add_argument("--mix", default="",
                    help="A:B 비율(예 20:80). 재료 있는 사례를 A(질의요지 그대로)·B(구어 변환)로 "
                         "배분해 돌린다 — 실사용(주소 없는 질문)에 맞춘 골든")
    args = ap.parse_args()

    suite = {}
    if args.suite:
        suite = json.loads(args.suite.read_text(encoding="utf-8"))
        suite_cases = [str(x) for x in suite.get("case_nos") or []]
        if not suite_cases:
            print("E2E suite에 case_nos가 없습니다", file=sys.stderr)
            return 2
        if args.cases:
            print("--suite와 --cases는 함께 쓸 수 없습니다", file=sys.stderr)
            return 2
        args.cases = ",".join(suite_cases)
        if not args.mix:
            args.mix = str(suite.get("mix") or "20:80")
        print(f"E2E suite {suite.get('name') or args.suite.stem} · {len(suite_cases)}건 · mix {args.mix}")

    if not INDEX.is_file():
        print("색인이 없습니다 — lawrag/pipeline/ingest_expc.py 먼저", file=sys.stderr)
        return 2
    cases = _cases(drop_ipa=args.no_ipa)
    if args.no_ipa:
        print(f"정보공개법 사례 제외 — 남은 {len(cases)}건")
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

    from lawrag.core.rag import index as index_mod
    idx = index_mod.current()
    if args.only:
        picked = [c for c in cases if c["case_no"] == args.only]
    elif args.holdout:
        tuned = set(json.loads(TUNED.read_text("utf-8"))["case_nos"]) \
            if TUNED.is_file() else set()
        picked = [c for c in cases if c["case_no"] not in tuned
                  and (c.get("answer") or "")][:args.limit or 10**9]
        print(f"홀드아웃 — 동결 {len(tuned)}건 밖 {len(picked)}건 (튜닝 금지 셋)")
    elif args.golden2:
        keep = {k for k, v in marked().items() if v.get("decisive_full")}
        picked = [c for c in cases if c["case_no"] in keep]
        print(f"골든 v2 — 항·호 정본이 있는 {len(picked)}건 (구어는 새로 쓴 것을 쓴다)")
    elif args.mix:
        picked = [c for c in cases if (c.get("answer") or "")][:args.limit or 10**9]
    else:
        picked = cases[:args.limit or 5]
    if args.material:
        before = len(picked)
        stat = {c["case_no"]: material_status(idx, c)[0] for c in picked}
        picked = [c for c in picked if stat[c["case_no"]] == "전부"]
        from collections import Counter
        print(f"재료 필터 — {before}건 중 회답 근거 조문이 창고에 전부 있는 {len(picked)}건만 "
              f"({dict(Counter(stat.values()))})")
    # 혼합 골든 — 재료 전부인 사례를 A:B 로 가른다. 배분은 결정론(안건번호 정렬 후
    # 등간격)이라 다시 돌려도 같은 사례가 같은 쪽이다. A 는 질의요지 원문에 인용이
    # 실제로 있는 사례에서만 고른다(인용 없는 원문은 어차피 B 다).
    mix_of: dict = {}
    if args.mix:
        a_pct = int(args.mix.split(":")[0])
        picked = [c for c in picked if material_status(idx, c)[0] == "전부"]
        picked.sort(key=lambda c: c["case_no"])
        n_a = round(len(picked) * a_pct / 100)
        a_ok = [c for c in picked if question_mode(idx, c.get("issue") or "") == "A"]
        step = max(len(a_ok) // max(n_a, 1), 1)
        a_set = {c["case_no"] for c in a_ok[::step][:n_a]}
        for c in picked:
            mix_of[c["case_no"]] = "A" if c["case_no"] in a_set else "B"
        n_b = len(picked) - len(a_set)
        print(f"혼합 골든 {args.mix} — 재료 전부 {len(picked)}건을 A {len(a_set)}(질의요지) "
              f"/ B {n_b}(구어 변환)로 배분")
    if args.cases:
        want = [c.strip() for c in args.cases.split(",") if c.strip()]
        picked = [c for c in picked if c["case_no"] in want]
        miss = [w for w in want if w not in {c["case_no"] for c in picked}]
        print(f"부분 실행 — {len(picked)}/{len(want)}건"
              + (f" · 없음: {' · '.join(miss)}" if miss else "")
              + "  (배분·질문지는 전체 판과 동일)")
    if not picked:
        print("고른 사례가 없습니다", file=sys.stderr)
        return 2
    rows = []
    print(f"검토 {len(picked)}건 실행 — 사례당 30~60초")
    for i, c in enumerate(picked, 1):
        try:
            use_colloq = args.colloquial or args.golden2 or mix_of.get(c["case_no"]) == "B"
            # 골든 v2 가 새로 쓴 구어를 우선한다. 옛 구어는 질의요지의 81%를
            # 삭제한 "요약"이라 쟁점·전제·주체가 함께 날아갔다(RETRIEVAL.md 8장).
            fresh = (marked().get(c["case_no"]) or {}).get("colloquial")
            txt = (fresh or colloquial_of(llm, c)) if use_colloq else None
            r = run_one(llm, idx, c, text=txt)
        except Exception as e:                       # 한 건이 죽어도 나머지는 돈다
            print(f"  !! {c['case_no']} 실패: {e}")
            continue
        rows.append(r)
        gold = labels.get(r["case_no"], "?")
        mark = {"적중": "○", "유보": "△", "오답": "✗", "미라벨": "·"}[
            verdict(gold, r["direction"])]
        print(f"  [{i}/{len(picked)}] {mark} {r['case_no']} "
              f"쟁점{r['issues']} 요건{r['subs']} → {r['direction']} (정답 {gold})"
              f" {r['sec']}s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.out or LAST
    from lawrag.core.rag import controls as controls_mod
    from lawrag.core.rag import evaluation as evaluation_mod
    control_rows = controls_mod.snapshot()
    out_path.write_text(json.dumps({
        "flow": "legal_review", "suite": suite, "rows": rows,
        "controls": {"fingerprint": controls_mod.fingerprint(control_rows),
                     "values": control_rows, "audit": controls_mod.audit(control_rows)},
        "engine": evaluation_mod.engine_snapshot(),
    }, ensure_ascii=False, indent=1), "utf-8")
    score(rows, labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
