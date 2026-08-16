"""검토 파이프라인 — 얇은 세로 관통 (docs/REVIEW.md §구현 순서 1단계).

    사실 추출 → 쟁점 도출 → 규범 조립 → 포섭 → 결론

다섯 단계를 **얇게** 관통시킨다. 요건 분해(논리 표지 승격)는 아직 없다 —
규범의 요건은 조문 텍스트에서 뽑은 얕은 목록이고, 그래도 **표 모양의 산출물이
나오는지**를 먼저 확인하는 것이 이 단계의 목적이다. 흔들리는 자리가 실측되면
그게 2단계(요건 분해)의 근거가 된다.

기존 자산을 그대로 쓴다 — 회수는 core/rag(검색 사다리·관계망 동반), 쟁점은
위키 카드(wikictx), 좌표는 구조 스토어. 검토는 새 검색기가 아니라 **회수 위에
얹는 판단 층**이다.

LLM 콜은 셋이다: 사실 추출 1 · 쟁점 도출 1 · 포섭 1(쟁점당). 결론은 포섭
결과에서 코드가 접는다 — 판정을 두 번 묻지 않는다.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

from core.rag import expand as expand_mod
from core.rag import wikictx
from core.rag.answer import assemble, sections_from_coords
from core.rag.search import search as run_search
from core.casereview.model import (Fact, Issue, Norm, Req, ReviewState, Sub,
                               Verdict, req_leaves)

log = logging.getLogger("core.casereview")

NORM_SECTIONS = 6         # 쟁점 하나에 조립할 규범 상한 — 판단은 넓이가 아니라 정확도다
REQ_MAX = 6               # 규범 하나에서 뽑을 요건 상한
ISSUE_MAX = 4             # 검토 하나에 세울 쟁점 상한 (질의응답 2장보다 넓다)
SUB_REQ_CAP = 18          # 포섭 한 콜에 넘길 요건 상한 — 넘기면 출력이 잘린다(실측)


# ---------------------------------------------------------------- ① 사실
FACT_SYSTEM = (
    "너는 법적 검토의 사실 정리자다. 입력에서 **법적으로 의미 있는 사실만** "
    "뽑아 주체·행위·대상으로 쪼갠다.\n"
    "규율: ① 감정·추측·도덕적 평가는 버리고 외부로 드러난 행위와 결과만 남긴다 "
    "(\"속이려 했다\" ✗ → \"월 10% 수익을 약속했다\" ○). ② 입력에 없는 사실을 "
    "지어내지 않는다. ③ 이미 벌어진 일이면 tense=과거, 앞으로 하려는 계획이면 "
    "tense=계획. ④ 한 항목에 하나의 행위만 담는다."
)
FACT_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "subject": {"type": "string"},
                       "action": {"type": "string"}, "object": {"type": "string"},
                       "tense": {"type": "string", "enum": ["과거", "계획"]}},
        "required": ["text", "subject", "action", "object", "tense"],
        "additionalProperties": False}}},
    "required": ["facts"], "additionalProperties": False,
}


def extract_facts(llm, text: str, limit: int = 8) -> list:
    """① 사실 확정 — 짧은 텍스트에서 사실 항목 3~5개.

    지금은 입력이 짧아 타임라인·증거 태깅이 무의미하다(docs/REVIEW.md §접는 것).
    Fact 의 when/evidence 칸은 비운 채 둔다 — 나중 기능이 그 칸을 채운다.
    """
    if llm is None:
        return [Fact(text=text.strip()[:200], subject="", action="", object="")]
    out = llm.structured("review.facts", FACT_SYSTEM, f"[입력]\n{text}",
                         FACT_SCHEMA, max_tokens=1200, effort="low")
    if out is None:
        return [Fact(text=text.strip()[:200])]
    facts = []
    for f in out.get("facts", [])[:limit]:
        facts.append(Fact(text=str(f.get("text", ""))[:300],
                          subject=str(f.get("subject", ""))[:60],
                          action=str(f.get("action", ""))[:80],
                          object=str(f.get("object", ""))[:80],
                          tense="계획" if f.get("tense") == "계획" else "과거"))
    return facts or [Fact(text=text.strip()[:200])]


# ---------------------------------------------------------------- ② 쟁점
ISSUE_SYSTEM = (
    "너는 법적 검토의 쟁점 도출자다. 정리된 사실과 쟁점 카드 목록을 보고, "
    "이 사안에 **실제로 걸리는 쟁점**을 고른다.\n"
    "규율: ① 카드에서 고르되 카드에 없는 쟁점이 사안의 핵심이면 card 를 비우고 "
    "새로 세워도 된다. ② 각 쟁점은 Yes/No 로 답할 수 있는 질문으로 압축한다 "
    "(\"이 서비스가 자본시장법상 '증권'에 해당하는가?\"). ③ gate 에는 그 법이 "
    "걸리는 이유를 관문 질문으로 적는다(\"수익을 기대하게 하고 자금을 모으는가\"). "
    "④ 검토는 여러 축을 함께 본다 — 하나만 고르지 말고 사안에 걸리는 만큼 세운다. "
    "⑤ 빈 배열은 **입력이 법적 검토 대상이 아닐 때만**이다(잡담·날씨 등). 사실에 "
    "규제 대상 행위 — 정보의 수집·제공·위탁, 업(業)으로 하는 행위, 인가·등록·신고가 "
    "필요할 수 있는 행위, 고객 자산·데이터의 취급 — 가 하나라도 있으면 반드시 그에 "
    "걸리는 쟁점을 세운다. 확신이 없어도 세우는 쪽이 맞다: 세운 쟁점은 뒤에서 "
    "요건별로 검증되지만, 안 세운 쟁점은 영영 검토되지 않는다."
)
ISSUE_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {
        "type": "object",
        "properties": {"question": {"type": "string"}, "gate": {"type": "string"},
                       "card": {"type": "string"},
                       "regulation": {"type": "string",
                                      "enum": ["수평", "수직", "충돌", ""]}},
        "required": ["question", "gate", "card", "regulation"],
        "additionalProperties": False}}},
    "required": ["issues"], "additionalProperties": False,
}


NET_MIN_TRIGGERS = 2      # 안전망이 서려면 트리거가 최소 이만큼 물어야 한다


def _issues_from_cards(facts: list, limit: int) -> list:
    """결정론 안전망 — 사실 문장을 쟁점 카드 트리거에 비춰 쟁점을 세운다.

    쟁점 도출은 검토 전체의 경첩이라 빈손이면 뒤의 네 단계가 없어진다. 그래서
    LLM 이 빈손이면 카드 트리거로 받는다. **다만 약한 매칭으로는 세우지
    않는다** — 골든 셋 25-0653 에서 '열람 경로' 사안에 트리거 하나("제공")가
    물어 「동의와 정보이용」 카드가 섰고, 남의 쟁점의 요건 18개가 전부 불명이
    되어 그럴듯한 유보를 만들었다. **틀린 쟁점은 빈손보다 나쁘다** — 빈손은
    '쟁점 실패'로 눈에 띄지만 틀린 쟁점은 원인을 숨긴다.
    """
    text = " ".join(f"{f.text} {f.action} {f.object}" for f in facts)
    out = []
    for s in wikictx.spot(text, limit=limit):
        if s.get("score", 0) < NET_MIN_TRIGGERS:
            continue                       # 약한 반응은 근거가 아니다
        out.append(Issue(question=f"{s['title']} — 이 사안에 걸리는가?",
                         gate=" · ".join(s.get("why", []))[:120],
                         axis=s.get("axis", ""), card=s["slug"],
                         by_net=True))
    return out


def spot_issues(llm, facts: list, limit: int = ISSUE_MAX) -> list:
    """② 쟁점 도출 — 사실을 법률의 언어로 번역한다.

    위키 쟁점 카드가 메뉴다(판단 축·조문 후보를 들고 온다). 카드 밖 쟁점도
    허용한다 — 카드는 축적된 지식이지 세상의 전부가 아니다. LLM 이 빈손이면
    카드 트리거(결정론)로 받는다 — 이 단이 무너지면 검토가 통째로 없어진다.
    """
    rows = [r for r in wikictx._rows() if r["slug"].startswith("쟁점/")]
    if llm is None or not rows:
        return _issues_from_cards(facts, limit)
    menu = "\n".join(f"- {r['slug']} | {r['title']} | 판단 축: "
                     f"{wikictx._meta(r['text']).get('판단 축', '')}" for r in rows)
    fact_txt = "\n".join(f"- [{f.id}] {f.subject} / {f.action} / {f.object}"
                         f" ({f.tense}) — {f.text}" for f in facts)
    # 이 콜만 effort 를 올린다 — 검토 전체가 여기 달렸다(뒤 단계는 이 결과의 파생).
    # 빈손이면 **먼저 한 번 더 묻는다**: 재시도는 같은 품질을 다시 뽑지만,
    # 안전망은 다른 품질(트리거 매칭)로 대체한다. 같은 값이면 같은 것으로
    # 메우는 쪽이 낫다 (골든 셋 25-0653 에서 안전망이 남의 쟁점을 세웠다).
    user = f"[정리된 사실]\n{fact_txt}\n\n[쟁점 카드 목록]\n{menu}"
    out = llm.structured("review.issues", ISSUE_SYSTEM, user, ISSUE_SCHEMA,
                         max_tokens=1500, effort="medium")
    if out is None or not out.get("issues"):
        out = llm.structured(
            "review.issues", ISSUE_SYSTEM,
            user + "\n\n[재시도] 앞선 시도가 쟁점을 세우지 못했다. 사실에 규제 "
                   "대상 행위가 있는지 다시 보고, 있으면 반드시 쟁점을 세워라.",
            ISSUE_SCHEMA, max_tokens=1500, effort="medium")
    if out is None:
        return _issues_from_cards(facts, limit)
    by_slug = {r["slug"]: r for r in rows}
    issues = []
    for it in out.get("issues", [])[:limit]:
        slug = str(it.get("card") or "").strip()
        row = by_slug.get(slug)
        reg = str(it.get("regulation") or "") or None
        issues.append(Issue(
            question=str(it.get("question", ""))[:200],
            gate=str(it.get("gate", ""))[:200],
            axis=(wikictx._meta(row["text"]).get("판단 축", "") if row else ""),
            regulation=reg if reg in ("수평", "수직", "충돌") else None,
            card=row["slug"] if row else None))
    return issues or _issues_from_cards(facts, limit)


# ---------------------------------------------------------------- ③ 규범
def _own_text(v, n: dict) -> str:
    """마디 **자신의** 본문 — 자식(호)의 몫은 뺀다.

    항의 자기 본문이 곧 "각 호 외의 부분"(줄기)이다. 이걸 안 빼면 항 텍스트가
    호 전부를 삼켜서 요건이 중복된다.
    """
    span = n.get("span") or [0, 0]
    a, b = span[0], span[1]
    kids = [k.get("span") or [b, b] for k in v.nodes if k.get("parent") == n["id"]]
    if kids:
        b = min([b] + [s[0] for s in kids])
    body = " ".join((v.blocks[i].get("text") or "")
                    for i in range(a, min(b, len(v.blocks))))
    return re.sub(r"\s+", " ", body).strip()


# 논리 표지 — 입안·심사 기준이 규격화한 표현이라 준(準)형식 언어다.
# 실측(2026-08-14, 호를 가진 줄기 8,450개): 어느 하나 15.7% · 열거 10.4% ·
# 다만 5.7% · 모두 1.6%. 나머지는 표지가 없어 관계를 **모른다** — 모르면
# op 를 비워 두고 개별 판정한다(추정으로 채우지 않는다).
_OR = re.compile(r"어느 하나")
_AND = re.compile(r"각 호[를의].{0,6}모두|모두 (?:갖추|충족|해당)")
_ALL_OF = re.compile(r"각 호의 사항.{0,24}(?:하여야|해야|알려야|기재|포함)")
_PROVISO = re.compile(r"(?:^|\s)다만,\s*")


def _mark_logic(req: Req) -> Req:
    """줄기의 표지를 읽어 `op` 를 채운다 (결정론, LLM 없음).

    이걸 안 읽으면 "10개 호 중 어느 하나"인 자리를 10번 개별 판정하고, 하나가
    충족돼도 나머지 9개의 불명이 남아 결론이 흐려진다(실측 불명률 68%의 큰 몫).
    """
    if not req.children:
        return req
    # 호 목록에 붙는 것은 **먼저 나온** 표지다. 한 줄기에 둘이 함께 오는 일이
    # 실재한다 — 개보법 제18조제3항: "다음 각 호의 사항을 …알려야 한다(AND).
    # 다음 각 호의 어느 하나의 사항을 변경하는 경우에도…" — 뒤 문장의 '어느
    # 하나'를 집으면 AND 를 OR 로 뒤집는다(실측에서 잡힌 오독).
    cands = []
    for op, rx in (("OR", _OR), ("AND", _AND), ("AND", _ALL_OF)):
        m = rx.search(req.text)
        if m:
            cands.append((m.start(), op))
    if cands:
        req.op = min(cands)[1]
    return req


def _split_proviso(req: Req) -> list:
    """단서(다만, …)를 별도 요건으로 뗀다 — 본문과 예외는 다른 판정이다."""
    m = _PROVISO.search(req.text)
    if not m or req.children:
        return [req]
    head, tail = req.text[:m.start()].strip(), req.text[m.end():].strip()
    if len(head) < 8 or len(tail) < 8:
        return [req]
    req.text = head
    return [req, Req(text=tail[:300], node=req.node, proviso=True,
                     id=(req.id or "") + "-단서")]


def _reqs_from_nodes(v, doc_id: str, node_id, cap: int = REQ_MAX) -> list:
    """요건을 **구조 마디**에서 세운다 (조 → 항 → 호).

    텍스트를 정규식으로 다시 자르지 않는다 — 조·항·호는 이미 마디로 파싱돼
    있고, 호가 곧 요건의 자연 단위다("1. 정보주체로부터 별도의 동의를 받은
    경우"). 문장 자르기는 판정 불가능한 조각(항의 머리글 등)을 만들어 불명을
    부풀렸다(실측 42/46).

    항에 호가 있으면 **항은 가지, 호가 잎**이다 — 항의 자기 본문(각 호 외의
    부분)은 잎들의 맥락으로 남는다. 논리 연산자(각 호의 어느 하나 = OR 등)는
    아직 비어 있다 — 2단계가 표지를 읽어 `op` 를 채운다.
    """
    n = v.by_id.get(node_id)
    if n is None:
        return []
    kids = [k for k in v.nodes if k.get("parent") == node_id]
    if not kids:                                   # 조가 통짜면 그 자체가 요건
        t = _own_text(v, n)
        return _split_proviso(Req(text=t[:400], node=node_id,
                                  id=Req.coord_id(doc_id, node_id))) if t else []
    out = []
    for k in kids:
        stem = _own_text(v, k)
        gk = [g for g in v.nodes if g.get("parent") == k["id"]]
        if gk:
            leaves = []
            for g in gk:
                t = _own_text(v, g)
                if t and not _is_deleted(t):       # 삭제된 호는 판정 대상이 아니다
                    leaves.append(Req(text=t[:260], node=g["id"],
                                      id=Req.coord_id(doc_id, g["id"])))
            if leaves:
                out.append(_mark_logic(Req(text=stem[:260], node=k["id"],
                                           id=Req.coord_id(doc_id, k["id"]),
                                           children=leaves)))
                continue
        if stem and not _is_deleted(stem):
            out.extend(_split_proviso(Req(text=stem[:400], node=k["id"],
                                          id=Req.coord_id(doc_id, k["id"]))))
        if len(out) >= cap:
            break
    return out


_DELETED = re.compile(r"^\s*(?:제[\d조의]+\s*|\d+\.\s*|[①-⑮]\s*)?삭제\s*(?:<[^>]*>)?\s*$")
# 조문 후보 한 줄을 (법령명, 조) 로 읽는다 — 법령명에 공백이 있으므로(「개인정보
# 보호법」·「자본시장과 금융투자업에 관한 법률」) 낫표 안은 통째로 받는다.
# 조는 없을 수 있다 ("전자금융거래법 법령군") — 그때는 좌표를 못 만든다.
_PROVISION = re.compile(
    r"(?:「(?P<a>[^」]+)」|(?P<b>[가-힣][가-힣\s·]{1,30}?(?:법률|법|규정|세칙|령)))"
    r"(?:\s*(?P<jo>제\d+조(?:의\d+)?))?")


def _is_deleted(text: str) -> bool:
    """삭제된 조문 — 본문이 "삭제 <2016.7.28>" 뿐이면 판정할 요건이 없다.

    실측(2026-08-14)에서 시행령 제32조(삭제)가 회수돼 포섭이 '해당없음'을
    내는 데 콜을 썼다. 판정은 옳았지만 회수가 낭비다 — 결정론으로 미리 뺀다.
    """
    return bool(_DELETED.match((text or "").strip()[:40]))


def _target_laws(spots: list) -> set:
    """쟁점 카드의 조문 후보에서 **법령명만** 추린다 (조문 번호는 버린다).

    회수 순위가 사안의 배경 법(증권사 사안이면 자본시장법)에 쏠려, 정작
    쟁점이 지목한 법(개인정보 보호법)이 상한에 밀려 안 들어오는 일이 있었다.
    법령명을 알아 두면 그 법의 구역을 앞자리에 세울 수 있다.
    """
    out = set()
    for s in spots:
        for p in s.get("provisions", []):
            m = _PROVISION.search(p.strip())
            if m:
                out.add(wikictx._pack(m.group("a") or m.group("b") or ""))
    return {o for o in out if o}


def _coords_of(idx, spots: list) -> list:
    """조문 후보 문자열을 구조 스토어의 좌표로 해석한다.

    "「개인정보 보호법」 제17조제1항" → (그 문서, 제17조 마디). 검색은 색인값
    (조문 제목·용어)이 질의 **안에** 있는지를 보므로 이런 인용 문자열을 못 문다
    — 카드가 법과 조를 이미 알려 준 이상 찾을 게 아니라 펴면 된다.
    법령명만 있고 조가 없으면(예: "전자금융거래법 법령군") 좌표를 만들지
    않는다 — 그건 검색이 할 일이다.
    """
    by_law: dict = {}
    for did, v in idx.docs.items():
        by_law.setdefault(wikictx._pack(v.name), (did, v))
    coords, seen = [], set()
    for s in spots:
        for p in s.get("provisions", []):
            m = _PROVISION.search(p.strip())
            if not m or not m.group("jo"):
                continue                   # 조가 없으면 좌표가 아니다 — 검색의 몫
            hit = by_law.get(wikictx._pack(m.group("a") or m.group("b") or ""))
            if hit is None:
                continue
            did, v = hit
            for n in v.nodes:
                if n.get("surface") == m.group("jo") and (did, n["id"]) not in seen:
                    seen.add((did, n["id"]))
                    coords.append({"doc_id": did, "node": n["id"],
                                   "via": "쟁점 조문", "why": p[:80]})
                    break
    return coords


# 입력 문면의 조문 인용 — 「법령」·대용어(같은 법/동법 ± 시행령) 뒤의 제N조.
# 편-조 체계(제4-19조)도 문다 (docs/LEGAL_DOMAIN §2 함정 ①).
_CITE = re.compile(
    r"「(?P<law>[^」]+)」"
    r"|(?P<ana>같은 법 시행령|같은 법|동법 시행령|동법)"
    r"|(?P<jo>제\d+(?:-\d+)?조(?:의\d+)?)")


def _cite_coords(idx, text: str) -> list:
    """입력이 문면에 인용한 조문 → 구조 스토어 좌표 (결정론, LLM 없음).

    질의요지·검토 의뢰문은 조문을 이미 밝힌다 — 골든 67건 중 65건이 문면
    인용을 갖고, 회답의 근거 조문(코퍼스 보유분) 58개 중 53개(91%)가 이
    인용만 좌표로 열어도 잡힌다(2026-08-16 결정론 실측). 그런데 회수가
    LLM 이 재작성한 쟁점 질문으로 검색하면서 원문에 있던 좌표가 증발했다
    (실측 26-0271: "같은 법 시행령 제41조제2항"이라 써 있는데 못 데려옴).
    카드 조문 후보를 좌표로 여는 _coords_of 와 같은 원리다 — **입력이 법과
    조를 이미 알려 준 이상 찾을 것이 아니라 펼 것이다.**

    대용어(같은 법·동법)는 직전 「법령명」으로 해소한다 — 회답 문체의 관례.
    단 그 표는 문서 선언이 아니라 문맥이라, 낫표 인용이 하나도 없으면 풀지
    않는다(발명 금지).
    """
    by_law: dict = {}
    for did, v in idx.docs.items():
        by_law.setdefault(wikictx._pack(v.name), (did, v))
    coords, seen, law = [], set(), ""
    for m in _CITE.finditer(text or ""):
        if m.group("law"):
            law = m.group("law").strip()
        elif m.group("ana"):
            if "시행령" in m.group("ana") and law and "시행령" not in law:
                law += " 시행령"
        elif m.group("jo") and law:
            hit = by_law.get(wikictx._pack(law))
            if hit is None:
                continue
            did, v = hit
            for n in v.nodes:                  # 문서 순서 = 본문이 부칙보다 먼저
                if n.get("surface") == m.group("jo") \
                        and (did, n["id"]) not in seen:
                    seen.add((did, n["id"]))
                    coords.append({"doc_id": did, "node": n["id"],
                                   "via": "문면 인용",
                                   "why": f"입력이 인용 — {law} {m.group('jo')}"})
                    break
    return coords


def _spot_for(issue: Issue, q: str) -> list:
    """쟁점이 이미 카드를 지목했으면 그 카드를 그대로 쓴다.

    쟁점 도출(LLM)이 카드를 골라 줬는데 트리거 매칭으로 **다시 발견**하려다
    놓치는 일이 있었다 — 카드 슬러그가 곧 답이므로 조회로 끝낸다. 카드가
    없을 때만 트리거로 찾는다.
    """
    if issue.card:
        for r in wikictx._rows():
            if r["slug"] == issue.card:
                return [wikictx._card_pick(r, ["쟁점 도출이 지목"], 0, "쟁점")]
    return wikictx.spot(q)


def build_norms(idx, issue: Issue, state: ReviewState,
                limit: int = NORM_SECTIONS) -> list:
    """③ 규범 조립 — 쟁점이 지목한 조문을 회수해 Norm 으로 세운다.

    회수는 기존 자산 그대로다: 쟁점 카드의 조문 후보로 질의를 넓히고
    (wikictx.expand_query — 검색 사다리 ①이 법령명을 문다), 검색·조립이
    관계망 동반(위임·준용·배제)까지 끌어온다. 검토는 새 검색기를 만들지
    않는다 — 회수 위에 판단을 얹는다.

    다만 **순서는 검토가 정한다**: 쟁점이 지목한 법령의 구역을 앞자리에
    세우고(배경 법에 밀리지 않게), 삭제된 조문은 뺀다. 지목한 법이 하나도
    안 왔으면 그 법령명만으로 한 번 더 찾는다 — 쟁점이 법을 아는데 회수가
    못 데려오는 것은 회수의 결함이지 쟁점의 결함이 아니다.
    """
    q = issue.question + " " + issue.gate
    spots = _spot_for(issue, q)
    qx = wikictx.expand_query(q, spots) if spots else q
    targets = _target_laws(spots)

    # 지목 조문은 **좌표로 연다** — 검색을 거치지 않는다. 색인값은 조문 제목이라
    # "「개인정보 보호법」 제17조제1항" 같은 문자열은 검색으로 안 물린다(실측).
    # ① 입력 문면의 인용(사안 자신의 좌표 — 가장 강한 신호)이 맨 앞,
    # ② 카드의 조문 후보가 그 뒤다.
    coords = _cite_coords(idx, state.question) \
        + (_coords_of(idx, spots) if spots else [])
    prior = sections_from_coords(idx, coords) if coords else []
    prior = [s for s in prior if not _is_deleted(s.text)]
    # ③ 필수 동반 — 착지 조문의 위임·배제·수임·준용을 판단 없이 동반한다.
    #    이 배선이 없어서 골든 26-0271이 "법 제35조는 왔는데 위임받은 시행령
    #    제41조가 안 오는" 회수 실패였다(위임 간선은 delegation.json 에 실재).
    #    27,318개 간선을 만들어 두고 검토 트랙만 안 쓰고 있었다.
    prior = expand_mod.expand_floor(idx, prior, cap=limit + 4)
    # 우선순위: 직행 좌표(탐색(…)) > 관계망 바닥(위임·배제·수임·준용) > 참조 확장
    prior.sort(key=lambda s: 0 if s.kind.startswith("탐색")
               else (2 if s.kind == "참조" else 1))

    have = {(s.doc_id, s.node) for s in prior}
    pool = [s for s in assemble(idx, run_search(idx, qx))
            if not _is_deleted(s.text) and (s.doc_id, s.node) not in have]
    # 좌표로 못 연 지목 법이 검색 결과에 있으면 그것도 앞자리로 올린다
    prior += [s for s in pool if wikictx._pack(s.doc) in targets]
    rest = [s for s in pool if s not in prior]
    norms = []
    for s in (prior + rest)[:limit]:
        v = idx.docs.get(s.doc_id)
        reqs = _reqs_from_nodes(v, s.doc_id, s.node) if v is not None else []
        if not reqs:                               # 마디가 비면 회수 본문으로 받는다
            body = re.sub(r"\s+", " ", s.text or "").strip()
            if not body:
                continue
            reqs = [Req(text=body[:400], node=s.node,
                        id=Req.coord_id(s.doc_id, s.node))]
        n = Norm(doc=s.doc, doc_id=s.doc_id, node=s.node, path=s.path,
                 reqs=reqs, effect="")
        norms.append(n)
        state.norms.append(n)
        issue.norms.append(n.id)
    return norms


# ---------------------------------------------------------------- ④ 포섭
SUB_SYSTEM = (
    "너는 법적 검토의 포섭 판정자다. 쟁점 하나에 대해, **요건마다** 사실을 대어 "
    "충족 여부를 판정한다.\n"
    "규율: ① 판정은 넷 중 하나 — 충족 / 불충족 / 불명 / 해당없음. ② 사실이 "
    "요건에 딱 맞지 않으면 **불명**으로 두어라 — 애매한 것을 충족으로 미는 것이 "
    "가장 큰 잘못이다. 불명은 실패가 아니라 이 사안의 진짜 쟁점을 가리키는 "
    "발견이다. ③ 판정마다 근거가 된 사실 id(facts)와 이유를 적는다. 근거 사실이 "
    "없으면 facts 는 빈 배열이고 판정은 대개 불명이다. ④ 조문에 없는 요건을 "
    "지어내지 마라 — 준 요건 목록 안에서만 판정한다. ⑤ reason 은 **한 문장**으로 "
    "짧게 적는다(80자 이내) — 길면 출력이 잘려 판정 전체가 버려진다."
)
SUB_SCHEMA = {
    "type": "object",
    "properties": {"subs": {"type": "array", "items": {
        "type": "object",
        "properties": {"req_id": {"type": "string"},
                       "judgment": {"type": "string",
                                    "enum": ["충족", "불충족", "불명", "해당없음"]},
                       "facts": {"type": "array", "items": {"type": "string"}},
                       "reason": {"type": "string"}},
        "required": ["req_id", "judgment", "facts", "reason"],
        "additionalProperties": False}}},
    "required": ["subs"], "additionalProperties": False,
}


def subsume(llm, issue: Issue, norms: list, facts: list) -> list:
    """④ 포섭 — 요건 × 사실 대조표를 만든다."""
    if llm is None or not norms:
        return []
    # 요건이 많으면 출력이 상한에 잘려 **판정 전체가 버려진다**(실측: 27개에서
    # JSON 미완결). 규범 순서가 곧 중요도 순(지목 조문이 앞)이라 앞에서 자른다.
    # 항의 줄기(각 호 외의 부분)는 판정 대상이 아니라 잎의 맥락으로 보여 준다.
    leaves: dict = {}
    lines: list = []

    def walk(reqs: list, indent: str = "  ") -> None:
        for r in reqs:
            if len(leaves) >= SUB_REQ_CAP:
                return
            if r.children:
                rel = {"OR": " ※ 아래 중 **하나만** 충족되면 된다",
                       "AND": " ※ 아래를 **모두** 충족해야 한다"}.get(r.op or "", "")
                if r.text or rel:
                    lines.append(f"{indent}〔{r.text[:90]}〕{rel}")
                walk(r.children, indent + "  ")
            else:
                leaves[r.id] = (n, r)
                lines.append(f"{indent}- [{r.id}] {r.text}")

    for n in norms:
        if len(leaves) >= SUB_REQ_CAP:
            break
        lines.append(f"◆ {n.doc} ▸ {n.path}")
        walk(n.reqs)
    fact_txt = "\n".join(f"- [{f.id}] {f.subject} / {f.action} / {f.object}"
                         f" ({f.tense}) — {f.text}" for f in facts)
    out = llm.structured(
        "review.subsume", SUB_SYSTEM,
        f"[쟁점]\n{issue.question}\n판단 축: {issue.axis}\n\n"
        f"[정리된 사실]\n{fact_txt}\n\n[요건 목록] "
        f"— ◆는 조문, 〔〕는 그 항의 머리글(맥락), [id]가 판정 대상이다\n"
        + "\n".join(lines),
        SUB_SCHEMA, max_tokens=4000, effort="low")
    if out is None:
        return []
    subs = []
    for s in out.get("subs", []):
        pair = leaves.get(str(s.get("req_id", "")).strip())
        if pair is None:
            continue                       # 지어낸 요건 id 는 버린다
        n, r = pair
        subs.append(Sub(issue_id=issue.id, norm_id=n.id, req_id=r.id,
                        req_text=r.text, judgment=s.get("judgment", "불명"),
                        facts=[f for f in s.get("facts", []) if isinstance(f, str)],
                        cites=[f"{n.doc} ▸ {n.path}"],
                        reason=str(s.get("reason", ""))[:300]))
    return subs


# ---------------------------------------------------------------- ⑤ 결론
def fold(req: Req, by_req: dict) -> str:
    """요건 트리를 판정 하나로 접는다 — 논리 연산자가 있는 자리만 접는다.

    OR  하나라도 충족이면 충족(형제의 불명은 묻지 않는다) · 전부 불충족이면 불충족
    AND 하나라도 불충족이면 불충족 · 전부 충족이면 충족
    미상 관계를 모르므로 전부 충족일 때만 충족, 그 밖은 불명 — **불충족으로
        단정하지 않는다**. 모르는 관계를 근거로 '불가'라고 말하지 않는 것이
        이 시스템의 규율이다.
    """
    if not req.children:
        return by_req.get(req.id, "불명")
    kids = [fold(c, by_req) for c in req.children]
    kids = [k for k in kids if k != "해당없음"]
    if not kids:
        return "해당없음"
    if req.op == "OR":
        if "충족" in kids:
            return "충족"
        return "불충족" if all(k == "불충족" for k in kids) else "불명"
    if req.op == "AND":
        if any(k == "불충족" for k in kids):
            return "불충족"
        return "충족" if all(k == "충족" for k in kids) else "불명"
    return "충족" if all(k == "충족" for k in kids) else "불명"


def conclude(issue: Issue, subs: list, norms: Optional[list] = None) -> Verdict:
    """⑤ 결론 — 포섭 결과를 코드가 접는다 (판정을 두 번 묻지 않는다).

    요건 트리가 있으면 **논리로 접는다**(fold): "각 호의 어느 하나"인 자리는
    하나만 충족되면 되므로 형제 아홉의 불명이 결론을 흐리지 않는다. 트리가
    없으면(norms 미전달) 예전처럼 평평하게 본다.

    접은 뒤의 규칙은 보수적이다: 불충족이 하나라도 있으면 '불가', 불명이 남으면
    '조건부'(그 요건이 이번 검토의 다툼 지점), 전부 충족이면 '가능'.
    판정이 하나도 없으면 '판단보류' — 모르는 것을 아는 척하지 않는다.
    """
    live = [s for s in subs if s.judgment != "해당없음"]
    if not live:
        return Verdict(issue_id=issue.id, conclusion="판단보류",
                       summary="요건에 댈 근거가 회수되지 않았습니다.")
    if norms:
        by_req = {s.req_id: s.judgment for s in subs}

        def judged(r: Req) -> bool:
            """포섭에 실제로 올라간 요건만 센다 — 상한(SUB_REQ_CAP)에 잘려
            판정조차 못 받은 요건을 '미해결'로 세면 다툼의 자리가 묻힌다."""
            return r.id in by_req or any(judged(c) for c in r.children)

        folded = [(r.id, fold(r, by_req))
                  for n in norms for r in n.reqs if judged(r)]
        folded = [(rid, j) for rid, j in folded if j != "해당없음"]
        unmet = [rid for rid, j in folded if j == "불충족"]
        unclear = [rid for rid, j in folded if j == "불명"]
    else:
        unmet = [s.req_id for s in live if s.judgment == "불충족"]
        unclear = [s.req_id for s in live if s.judgment == "불명"]
    if unmet:
        c, msg = "불가", f"요건 {len(unmet)}개가 충족되지 않습니다."
    elif unclear:
        c, msg = "조건부", f"요건 {len(unclear)}개가 사실관계로 확정되지 않습니다 — 이 지점이 다툼의 자리입니다."
    else:
        c, msg = "가능", "제시된 요건이 모두 충족됩니다."
    actions = []
    if unclear:
        actions.append("불명 요건에 대한 사실·자료 보완")
    if unmet:
        actions.append("구조 조정 또는 예외·특례 근거 검토")
    return Verdict(issue_id=issue.id, conclusion=c, summary=msg,
                   unmet=unmet + unclear, actions=actions)


# ---------------------------------------------------------------- 해석 판정
# 골든 67건 실측(2026-08-16)이 드러낸 트랙 오용의 교정이다:
#
#   시스템 출력  조건부 52 · 미정 10 · 부정 5 · **긍정 0**   (정답: 긍정 30)
#   조문까지 다 회수하고도 유보한 사례 24건
#
# 원인 둘. ⑴ 요건×사실 대조(포섭)는 적법성 검토(B트랙)의 기계다 — 해석례의
# 질문은 사실이 부족해서가 아니라 **문언의 의미가 다투어져서** 어렵다. 사실
# 대조에 해석 질문을 넣으면 "사실이 요건에 딱 맞지 않으면 불명" 규율이 불명을
# 양산한다(사례당 평균 13개). ⑵ 결론 규칙 "전부 충족이어야 가능"은 사례당
# 요건 평균 36개 아래에서 긍정을 도달 불능으로 만든다.
#
# 교정: 해석 트랙은 요건표 **위에** 문언 해석 판정을 한 콜 얹는다 — 법제처
# 회답과 같은 형식(사안 하나에 방향 하나). 규율은 유지된다: 코드가 접은
# **불충족은 판정보다 세다**(결정론이 먼저, LLM 은 남은 것만 — S5b·agent6 과
# 같은 원리). 요건표(Sub)와 보수적 fold 는 그대로 남는다 — 그것은 다툼 지점을
# 찾는 관측이고, 오류는 그걸 **답으로** 쓴 데 있었다.
INTERPRET_SYSTEM = (
    "너는 법령해석 판정자다. 질문과 회수된 조문(발췌)을 읽고 결론 방향을 "
    "판정한다 — 법제처 법령해석처럼.\n"
    "규율: ① 근거는 제시된 조문에서만 든다 — basis 에 그 조문 좌표를 그대로 "
    "적는다. 조문에 없는 근거로 판정하지 마라. ② 문언으로 답이 서면 긍정 "
    "또는 부정으로 판정한다 — 해석 질문은 문언·체계·입법취지로 답하는 것이지 "
    "사실이 더 있어야 답하는 것이 아니다. ③ **긍정과 부정은 대등한 답이다** — "
    "\"된다·해당한다·할 수 있다\"가 문언에서 서면 긍정으로 판정하라. 근거 "
    "조문이 부족하다는 이유로 부정을 고르지 마라: 회수가 빠뜨린 조문은 "
    "네 판정 재료가 아니라 이 시스템의 결함이고, 그때의 정직한 답은 조건부다. "
    "④ 조건부는 결론이 사안의 추가 사정에 갈리거나 **제시된 조문만으로는 "
    "문언이 서지 않을 때** 쓴다 — 틀린 단정보다 정직한 조건부가 낫다. "
    "⑤ [포섭 관측 — 불충족 요건]은 참고다: 그 요건이 이 사안의 결론을 가르는 "
    "핵심 요건이면 무겁게 보고, 부수 요건이면 결론을 좌우하지 않는다. 요건 "
    "하나의 불충족이 사안 전체를 부정으로 만들지는 않는다. ⑥ [해석 맥락 — "
    "지식 위키]는 축적된 선례의 **방향**이다 — 판단 축을 잡는 데 쓰되, 그 "
    "방향이 이 사안의 문언과 어긋나면 조문이 이기고, basis 에는 넣지 않는다. "
    "⑦ reason 은 세 문장 이내."
)
# 규율 ③·④·⑤ 개정 기록 (2026-08-16, 홀드아웃 113건 실측): 앞판 규율은
# "조건부를 확신 부족으로 쓰지 마라"(③) + "불충족과 모순되지 마라"(④)였고,
# 그 둘이 판정을 부정으로 끌었다 — 정답 긍정 52건 중 긍정 출력 4건(8%),
# 27건을 부정으로 뒤집음. 출력/정답 비율 긍정 0.19 · 부정 1.36. 포섭이 요건
# 36개를 대조하며 불충족을 잘 내는 구조라, "모순 금지"는 곧 "부정 강제"였다.
# 이제 불충족은 관측(핵심/부수 가림은 판정 몫), 조건부는 정직한 출구다.
INTERPRET_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["긍정", "부정", "조건부"]},
        "reason": {"type": "string"},
        "basis": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["direction", "reason", "basis"], "additionalProperties": False,
}
_INTERP_NORMS_MAX = 8        # 판정 콜에 넘기는 규범 수
_INTERP_CHARS = 700          # 규범당 발췌 — 판정은 조문 문언을 봐야 선다
# ── 판정 안정화 실측 (2026-08-16) ──────────────────────────────────────────
# 같은 state 로 판정 콜만 5회 반복(파이프라인 상류 고정):
#   하이쿠   16-0022 → 긍정2·조건부3 (같은 입력에 흔들림)   18-0261 → 긍정4·조건부1
#   소넷5    성공한 건 5/5 일치 — 단 max_tokens=600 이 사고 토큰에 먹혀 절반 넘게 잘림
# 4회차 뒤집힘 33%의 원인은 상류(쟁점 수·요건 수 분산은 뒤집힌 사례나 아닌 사례나
# 비슷)가 아니라 **판정 콜 자체의 분산**이었다. 표결 k=3 은 흔들리는 모델을 세 번
# 물은 것 — 비용 3배에 완화만 됐다. 흔들리지 않는 모델을 한 번 묻는 쪽이 맞다.
_INTERP_K = 1                # 표결 폐지 — 안정 모델 단일 콜 (k>1 은 실험용으로만)
_INTERP_MODEL = os.environ.get("REVIEW_INTERPRET_MODEL", "claude-sonnet-5")
_INTERP_MAX_TOKENS = 2400    # 600 → 2400: 사고 토큰 + JSON. 잘리면 llm.py 가 이름 붙여 보고
_CARD_CTX_CHARS = 1500       # 카드 한 장의 배경 상한
_CARD_CTX_MAX = 2            # 배경 카드 수


def _card_context(st: ReviewState) -> str:
    """쟁점이 지목한 카드의 **판단 기준**을 배경으로 편다.

    카드는 선례의 방향을 이미 갖고 있다 — 「다른 법률 근거의 문턱」에는
    "12건 중 11건 기각"이, 「경과조치의 존속」에는 "주체의 동일성이 유지되면
    보호도 유지된다"가 쓰여 있다. 골든 실측(20-0563): 이 카드를 안 보여 준
    판정이 문턱을 넓게 읽어 긍정을 냈다 — 정답은 기각(부정)이었다.
    규율은 answer.synthesize 규칙 ⑥과 같다: 방향 참고, basis 는 조문만.
    """
    slugs, seen = [], set()
    for i in st.issues:
        if i.card and i.card not in seen:
            seen.add(i.card)
            slugs.append(i.card)
    parts = []
    for row in wikictx._rows():
        if row["slug"] not in slugs or len(parts) >= _CARD_CTX_MAX:
            continue
        m = re.search(r"## 판단 기준\n(.+?)(?:\n## |\Z)", row["text"], re.S)
        body = (m.group(1) if m else row["text"]).strip()[:_CARD_CTX_CHARS]
        parts.append(f"《{row['title']}》\n{body}")
    if not parts:
        return ""
    return "\n\n[해석 맥락 — 지식 위키]\n" + "\n\n---\n\n".join(parts)


def interpret_case(llm, st: ReviewState) -> Optional[dict]:
    """사안 하나의 해석 판정 — 방향·이유·근거 조문. 판정 불가면 None.

    사안 수준이다(쟁점당이 아니라). 쟁점을 여럿 세워도 법제처 질문은
    하나고, 쟁점별 결론을 다시 접으면 부수 쟁점의 유보가 본 쟁점의 판정을
    희석한다(골든 실측 — 쟁점 평균 3개 중 결정적인 것은 대개 하나).

    **k회 표결이다** — 같은 안건의 중복 등재 쌍(18-0261=18-0583)에 한쪽은
    긍정, 한쪽은 부정이 나왔다(2026-08-16 실측). 같은 입력에 판정이 흔들리면
    한 콜은 동전 던지기다. 다수(2/3)가 방향을 정하고, 셋이 다 갈리면
    조건부로 내린다(모르는 것을 아는 척하지 않는다). agent6 의 자기일관성과
    같은 장치·같은 이유다.
    """
    if llm is None or not st.norms:
        return None
    uniq: dict = {}
    for n in st.norms:                        # 쟁점들이 같은 조를 공유하면 한 번만
        uniq.setdefault((n.doc_id, n.node), n)
    parts = []
    for n in list(uniq.values())[:_INTERP_NORMS_MAX]:
        body = " ".join(r.text for r in n.reqs)[:_INTERP_CHARS]
        parts.append(f"◆ {n.doc} ▸ {n.path}\n{body}")
    unmet = [s for s in st.subs if s.judgment == "불충족"]
    unmet_txt = ("\n\n[포섭 관측 — 불충족 요건] (참고 — 핵심 요건인지 판정이 가린다)\n"
                 + "\n".join(f"- {s.req_text[:100]} ({s.reason[:60]})"
                             for s in unmet[:6])) if unmet else ""
    issues_txt = "\n".join(f"- {i.question}" + (f" (판단 축: {i.axis})" if i.axis
                                                else "") for i in st.issues)
    user = (f"[질문]\n{st.question[:2000]}\n\n[도출된 쟁점]\n{issues_txt}\n\n"
            f"[회수된 조문]\n" + "\n\n".join(parts) + unmet_txt
            + _card_context(st))
    votes = []
    for _ in range(_INTERP_K):
        out = llm.structured("review.interpret", INTERPRET_SYSTEM, user,
                             INTERPRET_SCHEMA, max_tokens=_INTERP_MAX_TOKENS,
                             effort="medium", model=_INTERP_MODEL)
        if out is not None:
            votes.append(out)
    if not votes:
        return None
    tally: dict = {}
    for v in votes:
        tally[v["direction"]] = tally.get(v["direction"], 0) + 1
    top, n_top = max(tally.items(), key=lambda kv: kv[1])
    if n_top * 2 <= len(votes):               # 과반 없음 — 셋이 다 갈렸다
        top = "조건부"
    lead = next(v for v in votes if v["direction"] == top) \
        if top in tally else votes[0]
    return {"direction": top, "reason": str(lead["reason"])[:500],
            "basis": [str(b)[:120] for b in lead.get("basis", [])][:6],
            "votes": [v["direction"] for v in votes]}


# ---------------------------------------------------------------- 관통
def run(llm, idx, text: str, track: str = "해석") -> ReviewState:
    """다섯 단계를 얇게 관통한다 — 상태 하나를 단계들이 갱신한다."""
    t0 = time.perf_counter()
    st = ReviewState(question=text, track=track)  # type: ignore[arg-type]

    st.facts = extract_facts(llm, text)
    st.step("사실 확정", len(st.facts),
            " · ".join(f"{f.subject}:{f.action}" for f in st.facts[:3]))

    st.issues = spot_issues(llm, st.facts)
    st.step("쟁점 도출", len(st.issues),
            " · ".join(i.question[:28] for i in st.issues) or "걸린 쟁점 없음")
    if not st.issues:
        return st

    for issue in st.issues:
        norms = build_norms(idx, issue, st)
        subs = subsume(llm, issue, norms, st.facts)
        st.subs.extend(subs)
        st.verdicts.append(conclude(issue, subs, norms))
        issue.status = "해결" if subs else "미해결"
    st.step("규범 조립", len(st.norms),
            " · ".join(sorted({n.doc for n in st.norms}))[:80])
    n_or = sum(1 for n in st.norms for r in n.reqs if r.op == "OR")
    st.step("포섭", len(st.subs),
            f"충족 {sum(1 for s in st.subs if s.judgment == '충족')} · "
            f"불충족 {sum(1 for s in st.subs if s.judgment == '불충족')} · "
            f"불명 {len(st.unresolved())}"
            + (f" · OR 요건 {n_or}개는 접힌다" if n_or else ""))
    st.step("결론", len(st.verdicts),
            " · ".join(v.conclusion for v in st.verdicts))

    # 해석 트랙 — 요건표 위에 문언 해석 판정을 얹는다 (INTERPRET_SYSTEM 머리).
    # 코드가 접은 불충족이 있으면 프롬프트에 실려 판정을 구속한다(규율 ④).
    if track == "해석":
        st.overall = interpret_case(llm, st)
        if st.overall:
            st.step("해석 판정", 1,
                    f"{st.overall['direction']} — {st.overall['reason'][:60]}")
    log.info("검토 완료 — 쟁점 %d, 요건 %d, 불명 %d (%.0fms)",
             len(st.issues), len(st.subs), len(st.unresolved()),
             (time.perf_counter() - t0) * 1000)
    return st
