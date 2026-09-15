"""검토 파이프라인 — 얇은 세로 관통 (docs/REVIEW.md §구현 순서 1단계).

    사실 추출 → 쟁점 도출 → 규범 조립 → 포섭 → 결론

다섯 단계를 **얇게** 관통시킨다. 요건 분해(논리 표지 승격)는 아직 없다 —
규범의 요건은 조문 텍스트에서 뽑은 얕은 목록이고, 그래도 **표 모양의 산출물이
나오는지**를 먼저 확인하는 것이 이 단계의 목적이다. 흔들리는 자리가 실측되면
그게 2단계(요건 분해)의 근거가 된다.

기존 자산을 그대로 쓴다 — 회수는 lawrag/core/rag(검색 사다리·관계망 동반), 쟁점은
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

from lawrag.core.rag import definitions as definitions_mod
from lawrag.core.rag import expand as expand_mod
from lawrag.core.rag import promote as promote_mod
from lawrag.core.rag import termretrieve as termretrieve_mod
from lawrag.core.rag import wikictx
from lawrag.core.rag.answer import assemble, enforce_scope, sections_from_coords
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.search import search as run_search
from lawrag.core.casereview.model import (Fact, Issue, Norm, Req, ReviewState, Sub,
                               Verdict, req_leaves)

log = logging.getLogger("lawrag.core.casereview")

NORM_SECTIONS = int(control_value("review.norms_per_issue_max"))
REQ_MAX = int(control_value("review.requirements_per_norm_max"))
ISSUE_MAX = int(control_value("review.issues_max"))
SUB_REQ_CAP = int(control_value("review.sub_requirements_max"))
# 요건 한 조각의 글자 상한. **한 번 넓혀 봤다가 되돌렸다** (2026-08-17):
# 40 / 800 / 1200 으로 넓혀 고집 세트 11건을 재니 요건이 240→321 로 늘고 잘림·
# 타임아웃은 0 이었는데, 판정은 안 따라왔다 — 유보 3건이 풀려 1건만 정답, 2건은
# 오답(○0△8✗3 → ○1△5✗5). 근거는 오히려 나빠졌다(18-0124 과잉 1→4,
# 16-0182 근거 0/2→0/0). 요건 목록이 길어지자 판정이 **결정적 조문을 고르는 데서**
# 흔들린다. 병목은 재료의 양이 아니다 — 넓히면 잡음만 는다.
REQ_LEAF_CHARS = int(control_value("review.requirement_leaf_chars"))
REQ_STEM_CHARS = int(control_value("review.requirement_stem_chars"))
FACTS_MAX = int(control_value("review.facts_max"))
FACTS_MAX_TOKENS = int(control_value("review.facts_output_tokens"))
ISSUE_PROBES_MAX = int(control_value("review.issue_probes_max"))
PROBE_MAX_TOKENS = int(control_value("review.probe_output_tokens"))
_ISSUE_MAX_TOKENS = int(control_value("review.issue_output_tokens"))
                          # 예약이 아니다 — 안 쓰면 값이 0 이므로 넉넉히 잡는다.
                          # 잘리면 쟁점이 통째로 없어진다(상류라 제일 비싼 실패)


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


def extract_facts(llm, text: str, limit: int = FACTS_MAX) -> list:
    """① 사실 확정 — 짧은 텍스트에서 사실 항목 3~5개.

    지금은 입력이 짧아 타임라인·증거 태깅이 무의미하다(docs/REVIEW.md §접는 것).
    Fact 의 when/evidence 칸은 비운 채 둔다 — 나중 기능이 그 칸을 채운다.
    """
    if llm is None:
        return [Fact(text=text.strip()[:200], subject="", action="", object="")]
    out = llm.structured("review.facts", FACT_SYSTEM, f"[입력]\n{text}",
                         FACT_SCHEMA, max_tokens=FACTS_MAX_TOKENS, effort="low")
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
    "요건별로 검증되지만, 안 세운 쟁점은 영영 검토되지 않는다. "
    "⑤-2 question 과 gate 에는 **사실에 나온 법률용어를 원문 표기 그대로** 옮겨라 "
    "— 쪼개거나 풀어 쓰지 마라. 이 문장이 그대로 조문 검색 질의가 되므로 용어가 "
    "쪼개지면 엉뚱한 조문이 온다(실측 2026-08-17, 골든 24-0239: "
    "\"공시대상기업집단\"을 \"공시 대상 기업집단\"으로 풀어 써 검색이 '공시 의무' "
    "조문으로 갔다 — 정답인 이익제공 금지 조항은 회수되지 않았다). 그리고 사안이 "
    "묻는 **행위**(이익제공·위탁·겸직·열람 요구 등)를 반드시 question 에 넣어라 — "
    "배경 서술(지정·해당·설립 등)만 남으면 그 배경의 조문이 회수된다.\n"
    "⑥ 쟁점마다 why 에 **왜 이 사안에 이 쟁점이 걸리는지, 왜 이 카드인지**를 한두 "
    "문장으로 적고, confidence 에 핵심(질문이 직접 묻는 것)/부수(딸려 오는 것)를 "
    "가른다 — 부수 쟁점은 뒤에서 판정의 무게를 낮춘다.\n"
    "⑦ 쟁점마다 `조문질의`를 1~2개 쓴다 — **이 쟁점이 찾는 조문이 실제로 쓰였을 "
    "법한 문체의 서술문**이다. question·gate 는 판정의 언어(\"…에 해당하는가\", "
    "\"…요건을 명시하는가\")라 조문 검색에 독이 된다(실측: 심사 언어로 국세기본법을 "
    "뒤지니 정답 '국세행정에 대한 협조' 조는 40위 밖, 조문 문체 한 문장이면 1위). "
    "규칙: · 조문이 쓰는 표현 — '…할 수 있다', '…하여야 한다', '…요청할 수 있다', "
    "'…에 관하여는 …을 준용한다', '이 법 시행 당시'. · 구어·질문형·심사 언어 금지 — "
    "'해당하는가', '명시되어 있는가', '요건을 갖추었는가'를 쓰지 않는다. · 사안의 "
    "주체와 핵심 행위를 조문의 낱말로 넣는다(국세청→세무공무원, 넘겨줌→제공·협조 요청). "
    "· 카드의 판단 축을 베끼지 마라 — 판단 축은 심사 기준이지 조문 문장이 아니다. "
    "· 법령명·조번호는 넣지 마라(어휘 채널이 따로 문다) — 지어내면 엉뚱한 데 착지한다. "
    "· 두 개를 쓸 때는 하나는 조문 직역형, 하나는 핵심 행위·주체만 남긴 짧은 형으로."
)
ISSUE_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {
        "type": "object",
        "properties": {"question": {"type": "string"}, "gate": {"type": "string"},
                       "card": {"type": "string"},
                       "regulation": {"type": "string",
                                      "enum": ["수평", "수직", "충돌", ""]},
                       "why": {"type": "string"},
                       "confidence": {"type": "string", "enum": ["핵심", "부수"]},
                       # 회수용 조문 문체 서술문 1~2개 — 벡터 채널 전용 (Issue.probes)
                       # (maxItems 는 구조화 출력 스키마가 거부한다 — 파서가 [:2] 로 자른다)
                       "조문질의": {"type": "array", "items": {"type": "string"}}},
        "required": ["question", "gate", "card", "regulation", "why", "confidence",
                     "조문질의"],
        "additionalProperties": False}}},
    "required": ["issues"], "additionalProperties": False,
}


NET_MIN_TRIGGERS = int(control_value("review.net_triggers_min"))


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
                         max_tokens=_ISSUE_MAX_TOKENS, effort="medium")
    if out is None or not out.get("issues"):
        log.info("쟁점 1차 빈손 — 재시도한다 (사실 %d개)", len(facts))
        out = llm.structured(
            "review.issues", ISSUE_SYSTEM,
            user + "\n\n[재시도] 앞선 시도가 쟁점을 세우지 못했다. 사실에 규제 "
                   "대상 행위가 있는지 다시 보고, 있으면 반드시 쟁점을 세워라.",
            ISSUE_SCHEMA, max_tokens=_ISSUE_MAX_TOKENS, effort="medium")
    if out is None:
        log.warning("쟁점 콜이 두 번 다 실패 — 카드 트리거(안전망)로 받는다")
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
            card=row["slug"] if row else None,
            why=str(it.get("why", ""))[:300],
            core=(it.get("confidence") != "부수"),
            probes=[str(x).strip()[:wikictx.PROBE_MAX_CHARS]
                    for x in (it.get("조문질의") or [])[:ISSUE_PROBES_MAX]
                    if str(x).strip()]))
    if issues:
        return issues
    net = _issues_from_cards(facts, limit)
    if not net:
        # 무성 실패 — 검토가 통째로 없어지는데 로그가 없으면 정상 완주와 구별이
        # 안 된다(혼합 골든 v2 07-0261: 쟁점0·3.6초가 실패 한 줄 없이 지나갔다).
        log.warning("쟁점 0 — LLM 두 번 다 빈손이고 카드 트리거도 안 물었다 "
                    "(사실 %d개) · 이 사례는 검토 없이 끝난다", len(facts))
    return net


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
    return [req, Req(text=tail[:REQ_STEM_CHARS], node=req.node, proviso=True,
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
        return _split_proviso(Req(text=t[:REQ_STEM_CHARS], node=node_id,
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
                    leaves.append(Req(text=t[:REQ_LEAF_CHARS], node=g["id"],
                                      id=Req.coord_id(doc_id, g["id"])))
            if leaves:
                out.append(_mark_logic(Req(text=stem[:REQ_LEAF_CHARS], node=k["id"],
                                           id=Req.coord_id(doc_id, k["id"]),
                                           children=leaves)))
                continue
        if stem and not _is_deleted(stem):
            out.extend(_split_proviso(Req(text=stem[:REQ_STEM_CHARS], node=k["id"],
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


# ── 카드 조문 후보 → 좌표 (퇴역, 2026-08-18) ────────────────────────────
# 아래 둘은 회수 경로에서 뺐다 — 카드 조문 후보는 컴파일 사례의 좌표라 사안이
# 다르면 다른 조를 가리킨다(build_norms 머리의 18-0124 실측). 코드는 남긴다:
# 사용자·피드백 루프가 **승인한** 쟁점↔조문 연결을 좌표로 여는 고리가 생기면
# 그때 이 함수들이 그 연결(카드 메타가 아니라 승인 원장)을 읽어 되살아난다.


def _target_laws(spots: list) -> set:
    """쟁점 카드의 조문 후보에서 **법령명만** 추린다 (조문 번호는 버린다).

    (퇴역 — 회수 경로 밖. 위 블록 머리.) 회수 순위가 사안의 배경 법에 쏠려
    쟁점이 지목한 법이 상한에 밀리던 시절의 앞자리 승격 장치였다.
    """
    out = set()
    for s in spots:
        for p in s.get("provisions", []):
            m = _PROVISION.search(p.strip())
            if m:
                out.add(wikictx._pack(m.group("a") or m.group("b") or ""))
    return {o for o in out if o}


def _coords_of(idx, spots: list) -> list:
    """조문 후보 문자열을 구조 스토어의 좌표로 해석한다. (퇴역 — 회수 경로 밖.)

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
    **입력이 법과 조를 이미 알려 준 이상 찾을 것이 아니라 펼 것이다.** 이것이
    좌표를 여는 유일한 통로다 — 사안 **자신**이 쓴 좌표라 사안과 어긋날 수 없다
    (카드 조문 후보는 남의 사례 좌표라 여기서 뺐다, build_norms 머리).

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
    # 엔진 스위치(issue_spot)는 질의응답과 검토가 같이 본다 — 사용자가 끄면
    # 트리거 매칭도 검토 트랙에서 빠진다(카드 직접 지목은 스위치 밖이다).
    from lawrag.core.rag import switches as switches_mod
    return wikictx.spot(q) if switches_mod.is_on("issue_spot") else []


_ART_SURFACE = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")


def _article_of(v, node_id):
    """마디를 감싸는 **조** 마디로 올린다 — 호·항으로 착지해도 규범은 조 단위다.

    판정 입력은 조의 마디 전문이므로(제9조 ①항 제5호가 답이라도 ①항 머리글이
    있어야 읽힌다) 벡터가 호에 착지하면 그 조를 연다. 조가 없으면(별표·부칙
    머리) 그 마디 그대로다.
    """
    cur = node_id
    seen: set = set()
    while cur is not None and cur not in seen:
        n = v.by_id.get(cur)
        if n is None:
            break
        if _ART_SURFACE.match(n.get("surface") or ""):
            return cur
        seen.add(cur)
        cur = n.get("parent")
    return node_id


def _vector_sections(idx, query: str, exclude: set, topk: int = 12) -> list:
    """벡터 채널 — 쟁점 문장(법률 문체)으로 구역을 찾아 조 단위 Section 으로.

    같은 조에 여러 마디가 착지하면 하나로 접는다(그게 곧 표다). 실패하면 빈
    목록 — 호출부는 벡터가 없다와 못 한다를 구별할 필요가 없다.
    """
    from lawrag.core.rag import vector as vector_mod
    from lawrag.core.rag import verdicts as verdicts_mod
    from lawrag.core.rag.answer import SECTION_CHARS, Section
    try:
        nodes = vector_mod.search(query, topk=topk, doc_ids=idx.scope)   # 진입은 스코프 안만
    except Exception as exc:                          # 모델·색인 부재
        from lawrag.runtime.content_snapshot import ContentSnapshotError

        if isinstance(exc, ContentSnapshotError):
            raise
        log.warning("벡터 채널 실패 — 어휘만으로 간다: %s", exc)
        return []
    out, seen = [], set()
    for doc_id, node, cos in nodes:
        v = idx.docs.get(doc_id)
        if v is None:
            continue
        art = _article_of(v, node)
        key = (doc_id, art)
        if key in seen or key in exclude:
            continue
        # 진입 제외 — 질의응답 백로그에서 "검색무관→진입제외"로 승인된 좌표는
        # 검토 트랙의 벡터 진입에서도 뺀다(같은 규율, 참조 동반으로는 온다).
        if (verdicts_mod.is_entry_blocked(doc_id, node)
                or verdicts_mod.is_entry_blocked(doc_id, art)):
            continue
        seen.add(key)
        n = v.by_id.get(art)
        out.append(Section(
            n=0, doc_id=doc_id, doc=v.name, node=art,
            path=v.path(art) or v.name, page=(n or {}).get("page"),
            kind="벡터", matched=f"코사인 {cos:.2f}",
            text=v.section_outline(n, cap=SECTION_CHARS) if n else ""))
    return out


_TERMS_CACHE: dict = {}


def _legal_terms() -> set:
    """창고의 정의 조항에서 뽑은 법률용어 — 질의에서 **쪼개지지 않게 지킨다**.

    골든 24-0239 실측(2026-08-17): 쟁점이 "공시대상기업집단"을 "공시 대상 기업집단"
    으로 풀어 쓰자 어휘 검색이 '공시 의무' 조문을 물었고 정답(제47조 이익제공 금지)은
    회수되지 않았다. 같은 회수기가 용어를 온전히 준 질의에서는 제47조를 정확히
    데려온다 — 회수기의 결함이 아니라 질의의 결함이다.

    두 곳에서 긁는다:

    ① 정의 조항(제N조 "용어의 뜻")의 각 호 — «"용어"란» 꼴. 창고 42개 문서 중
       14개가 정의 조를 갖고 있다.
    ② **본문 어디서든 «(이하 "X"라 한다)» 꼴** — 이게 없으면 정작 필요한 용어를
       놓친다. 24-0239 의 "공시대상기업집단"은 제2조가 아니라 제26조제1항의
       «제31조제1항 전단에 따라 지정된 공시대상기업집단(이하 "공시대상기업집단"
       이라 한다)» 에서 정의된다 — 정의 조만 보면 사전에 안 들어온다(실측).

    ②가 훨씬 흔하다. 법률은 긴 지시를 한 번 풀어 쓰고 그 뒤로는 약칭을 쓴다.
    """
    if _TERMS_CACHE:
        return _TERMS_CACHE["terms"]
    from lawrag.core.rag import index as index_mod
    pat = re.compile(r"[\"“「]([^\"”」「]{3,30})[\"”」]\s*"
                     r"(?:\([^)]{0,20}\))?\s*(?:이?란|라\s*함은)")
    # «(이하 "X"라 한다)» · «(이하 "X"이라 한다)» — 본문 어디서든
    alias = re.compile(r"이하\s*[\"“]([^\"”]{3,30})[\"”]\s*(?:이)?라\s*(?:고\s*)?한다")
    out: set = set()
    try:
        idx = index_mod.current()
    except Exception:                                  # 색인 부재 — 지킬 것이 없다
        _TERMS_CACHE["terms"] = out
        return out
    for v in idx.docs.values():
        # ① 정의 조항
        for n in v.nodes:
            if (n.get("surface") or "") not in ("제2조", "제3조"):
                continue
            head = v.section_outline(n, cap=300) or ""
            if "용어의 뜻" not in head and "용어의 정의" not in head:
                continue
            for k in v.nodes:
                if k.get("parent") != n["id"]:
                    continue
                m = pat.search(v.section_outline(k, cap=300) or "")
                if m:
                    out.add(m.group(1).strip())
            break
        # ② 본문의 «(이하 "X"라 한다)» — 블록 텍스트를 한 번에 훑는다
        for blk in (v.blocks or []):
            txt = blk.get("text") if isinstance(blk, dict) else str(blk)
            for m in alias.finditer(txt or ""):
                out.add(m.group(1).strip())
    _TERMS_CACHE["terms"] = out
    return out


def _keep_terms(q: str) -> str:
    """질의에 쪼개진 법률용어의 원문 표기를 덧붙인다. **지금은 쓰지 않는다.**

    24-0239 를 고치려고 만들었다가 직접 시험에서 역효과가 확인됐다(2026-08-17):
    "공시대상기업집단"을 덧붙이니 그 용어가 제목에 든 조(제31·35·38·41조 —
    전부 '공시' 계열)가 상위로 올라와 정답 제47조(이익제공 금지)를 더 밀어냈다.
    온전한 질의에서도 제47조가 1순위에서 뒤로 밀렸다.

    **배경 용어를 증폭하면 판별 낱말이 묻힌다.** 이 사안에서 답을 가르는 낱말은
    "이익제공"이고 "공시대상기업집단"은 배경이다. 질의 후처리로 용어를 보태는
    방식 자체가 틀렸다 — 무엇이 배경이고 무엇이 판별인지는 질의 밖에서 알 수 없다.

    올바른 자리는 **쟁점 프롬프트**다(ISSUE_SYSTEM ⑤-2): 사실의 법률용어를 원문
    표기로 옮기고 사안이 묻는 **행위**를 반드시 넣게 한다. 용어 사전(_legal_terms)
    은 남겨 둔다 — 1154개 용어는 다른 데(용어 인식·해당성 물음 판정)에 쓸모가 있다.
    """
    terms = _legal_terms()
    if not terms:
        return q
    flat = re.sub(r"\s+", "", q)
    add = [t for t in terms if len(t) >= 5 and t not in q and re.sub(r"\s+", "", t) in flat]
    return q + ("  " + " ".join(sorted(add)) if add else "")


def _review_query(q: str, spots: list) -> str:
    """검색 질의 = 쟁점 문장 + 카드의 조문질의(probe). **조문 후보 텍스트는 안 넣는다.**

    카드 조문 후보(「…법률」 제47조제1항)는 그 카드를 컴파일할 때 본 사례의
    좌표라 사안이 다르면 무관한데, 질의에 실리면 "제47조"라는 조 제목이 엉뚱한
    법의 제47조에 정확 일치로 물린다(혼합 골든 20:80 실측 2026-08-17: 06-0131
    구어판이 자본시장법 제47조 하나 물고 정보공개법은 0건).
    """
    probes = []
    pq = wikictx._pack(q)
    for s in spots or []:
        pr = (s.get("probe") or "").strip()
        if pr and wikictx._pack(pr) not in pq and pr not in probes:
            probes.append(pr)
    return q + ("\n[법률용어 질의] " + " ".join(probes) if probes else "")


def _interleave(a: list, b: list) -> list:
    out, seen = [], set()
    for i in range(max(len(a), len(b))):
        for s in (a[i:i + 1] + b[i:i + 1]):
            k = (s.doc_id, s.node)
            if k not in seen:
                seen.add(k)
                out.append(s)
    return out


_DEFN_HEAD = re.compile(r"용어의\s*뜻|용어의\s*정의")


def _sibling_and_defn(idx, secs: list, cap: int = 8) -> list:
    """회수한 조의 **이웃 조**와 그 법의 **정의 조**를 함께 연다.

    골든 v2 첫 실행에서 놓친 마디 15개를 전수로 갈랐더니 셋으로 나뉘었다:

        둘째 법을 못 따라감   5개   백지 지시("다른 법률에 특별한 규정")라 어휘 고리 0
        정의 조항을 안 가져옴 4개   실체 규정은 잡고 정의를 놓친다
        같은 법 인접 조 못 감 5개   20-0569 는 제28조의2·제28조의5 를 잡고 그 사이
                                   제28조의4 를 놓쳤다 — 같은 절 안 이웃이다

    이 함수는 뒤의 둘을 한 번에 치려고 만들었다. **지금은 쓰지 않는다** — 두 번
    시도해 두 번 실패했다(2026-08-17, 골든 v2 네 판):

        run1  확장 없음          회수 51/66 (77%)   ← 기준선
        run2  확장을 앞자리에     48/66 (73%)   상한 6 밖으로 정답이 밀려났다
        run3  확장을 뒷자리로     47/66 (71%)   밀어내기를 막았는데도 안 오름
        run4  run3 재현           45/66 (68%)   같은 코드 두 판 폭 = 2개

    겨냥했던 세 사례(07-0261·17-0387·18-0124)가 **두 판 모두에서 하나도 살아나지
    않았다.** run2 에서 올라간 것은 확장 효과가 아니라 요동이었다.

    왜 안 먹혔는지는 아직 모른다. 다시 시도하려면 **회수 파이프라인에 넣기 전에
    "이 확장이 정답 마디를 실제로 데려오는가"를 오프라인으로 먼저 확인**하라 —
    파이프라인에 꽂고 전체 지표로 재면 요동에 묻힌다(폭 2개에 효과 0개).

    정의 조는 그 법의 "용어의 뜻" 조 하나만 연다. 아침에 용어 사전(116개)으로
    질문에서 용어를 뽑아 여는 방식을 시도했다가 정밀도 12%로 접었는데, 여기서는
    **이미 회수한 법**에 대해서만 열므로 엉뚱한 법의 정의 조가 딸려오지 않는다.
    """
    from lawrag.core.rag.answer import SECTION_CHARS, Section
    have = {(s.doc_id, s.node) for s in secs}
    out: list = []
    seen_defn: set = set()
    for s in list(secs)[:cap]:
        v = idx.docs.get(s.doc_id)
        if v is None:
            continue
        node = v.by_id.get(s.node)
        if node is None:
            continue
        # ── 이웃 조 — 같은 부모 아래 앞뒤 하나씩
        sibs = [k for k in v.nodes if k.get("parent") == node.get("parent")
                and _ART_SURFACE.match(k.get("surface") or "")]
        ids = [k["id"] for k in sibs]
        if node["id"] in ids:
            i = ids.index(node["id"])
            for j in (i - 1, i + 1):
                if 0 <= j < len(ids) and (s.doc_id, ids[j]) not in have:
                    have.add((s.doc_id, ids[j]))
                    sib = v.by_id.get(ids[j]) or {}
                    out.append(Section(
                        n=0, doc_id=s.doc_id, doc=v.name, node=ids[j],
                        path=v.path(ids[j]) or v.name, page=sib.get("page"),
                        kind="이웃", matched=sib.get("surface") or "",
                        text=v.section_outline(sib, cap=SECTION_CHARS) if sib else ""))
        # ── 정의 — 이 조문에 **쓰인** 정의어의 호만 (definitions.terms_in, 2026-08-18).
        #    옛 판은 그 법의 "용어의 뜻" 조 하나를 통째로 열었다 — 개보법이면 호
        #    열 개가 실려 판정이 그 안에서 스스로 찾아야 했다. 이제 개보법
        #    제17조엔 개인정보처리자(5호)·개인정보(1호)·정보주체(3호)·처리(2호)만.
        #    쓰인 정의어가 하나도 없으면 옛 판처럼 관할 정의 조 하나로 폴백.
        used = definitions_mod.terms_in(v, s.node)
        if used:
            for d in used:
                if (s.doc_id, d["node"]) in have:
                    continue
                have.add((s.doc_id, d["node"]))
                dn = v.by_id.get(d["node"]) or {}
                out.append(Section(
                    n=0, doc_id=s.doc_id, doc=v.name, node=d["node"],
                    path=v.path(d["node"]) or v.name, page=dn.get("page"),
                    kind="정의", matched=f"'{d['term']}'",
                    text=v.section_outline(dn, cap=SECTION_CHARS) if dn else ""))
            continue
        if s.doc_id in seen_defn:
            continue
        seen_defn.add(s.doc_id)
        for k in v.nodes:
            if not _ART_SURFACE.match(k.get("surface") or ""):
                continue
            if "부칙" in (v.path(k["id"]) or ""):
                continue
            head = v.section_outline(k, cap=300) or ""
            if not _DEFN_HEAD.search(head) or _is_deleted(head):
                continue
            if (s.doc_id, k["id"]) not in have:
                have.add((s.doc_id, k["id"]))
                out.append(Section(
                    n=0, doc_id=s.doc_id, doc=v.name, node=k["id"],
                    path=v.path(k["id"]) or v.name, page=k.get("page"),
                    kind="정의", matched=k.get("surface") or "",
                    text=v.section_outline(k, cap=SECTION_CHARS)))
            break
    return out


def build_norms(idx, issue: Issue, state: ReviewState,
                limit: int = NORM_SECTIONS) -> list:
    """③ 규범 조립 — 쟁점이 지목한 조문을 회수해 Norm 으로 세운다.

    회수 통로 넷 — ① 입력 문면 인용의 좌표(주소 펴기) ② 카드 조문 후보의 좌표
    (사안이 그 법을 말할 때만) ③ ①②의 관계망 바닥(위임·배제·준용) ④ 검색 =
    **어휘 앵커와 벡터를 둘 다 돌려 합류**. 순서는 ①②③ 이 앞이고 ④ 가 남는
    자리를 채운다.

    ④ 가 낙하식이 아닌 이유(2026-08-17 혼합 골든 20:80 실측): 옛 사다리
    (core.rag.search.search)는 정확 일치가 하나라도 걸리면 벡터를 안 돌렸다.
    주소 없는 질문(B) 41건의 조문 회수가 15%였고, 실패 33건 대부분이 "제47조"·
    "공공기관"·"적용대상" 같은 **우연한 조 제목 일치**가 정확 단에 걸려 벡터가
    한 번도 안 돈 경우였다 — 벡터만 따로 돌리면 정답 조가 1~4위였다(06-0131
    정보공개법 제9조 3위 · 07-0261 공공기관운영법 제27조 1위). 주소 있는
    질문(A)은 ①이 답을 펴므로 ④의 방식에 영향받지 않는다.
    """
    q = issue.question + " " + issue.gate
    spots = _spot_for(issue, q)
    qx = _review_query(q, spots)

    # 지목 조문은 **좌표로 연다** — 검색을 거치지 않는다. 색인값은 조문 제목이라
    # "「개인정보 보호법」 제17조제1항" 같은 문자열은 검색으로 안 물린다(실측).
    # 좌표를 여는 것은 **입력 문면의 인용**(사안 자신의 좌표 — 가장 강한 신호)
    # 하나뿐이다. 카드의 조문 후보는 열지 않는다(2026-08-18 사용자 결정) —
    # 그것은 카드를 컴파일할 때 본 사례들의 좌표라 사안이 다르면 다른 조를
    # 가리킨다. 실측 18-0124: 쟁점기가 국세기본법을 정확히 지목했는데 카드
    # 후보(제81조의13 비밀 유지)가 좌표로 열려 앞자리를 잡고, 그 동반(벌칙·정의)
    # 까지 딸려 와 규범 6칸을 채우는 바람에 벡터가 찾을 정답(제84조 국세행정에
    # 대한 협조)이 실릴 자리가 없었다. 카드의 소임은 질문을 조문 문체로 옮기는
    # 것(probe → 벡터)이지 좌표 연결이 아니다. 사용자·피드백 루프가 승인한
    # 연결만 좌표가 될 수 있고, 그 고리는 아직 없다.
    coords = _cite_coords(idx, state.question)
    # 승인 원장의 **활성** 연결 — 어렵게(깔때기) 찾아 사람이 승인한 착지는 다음
    # 질의에서 검색 없이 연다(promote.direct_hits: 같은 질문 → 비슷한 질문).
    # 잠정은 안 연다 — 오답 착지도 착지다.
    coords += promote_mod.direct_hits(state.question, index=idx)
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
    # ④ 검색 — 어휘 앵커(정확·부분·본문 사다리)와 벡터(쟁점 문장 → 조)를 **둘 다**
    #    돌려 번갈아 합류한다. 벡터가 앞이다: 주소 없는 질문에서 답을 찾는 채널이
    #    벡터이고, 어휘 앵커는 우연한 제목 일치일 때가 많다(도크스트링 실측).
    lex = [s for s in assemble(idx, run_search(idx, qx))
           if not _is_deleted(s.text) and (s.doc_id, s.node) not in have]
    # 벡터 채널은 **조문 문체 서술문(probes)** 으로 간다 — question·gate 는
    # 판정의 언어(심사)라 벡터가 엉뚱한 조를 문다(실측 18-0124: 심사 언어로는
    # 정답 제84조가 40위 밖, 조문 문체 한 문장이면 1위). 어휘 채널은 여전히
    # question·gate·법령명을 문다 — 채널마다 무는 문장이 다르다(wikictx.vector_query
    # 실측: 법령명 섞은 질의가 코사인은 높고 내용은 최악). probes 가 없으면(옛
    # 쟁점·안전망 쟁점) qx 로 폴백. probe 둘이면 둘 다 돌려 순위 번갈아 합류.
    vqs = [pr for pr in (issue.probes or []) if pr] or [qx]
    vec_runs = [[s for s in _vector_sections(idx, vq, have, topk=limit * 2)
                 if not _is_deleted(s.text)] for vq in vqs]
    vec = vec_runs[0] if len(vec_runs) == 1 else _interleave(vec_runs[0], vec_runs[1])
    pool = _interleave(vec, lex)
    rest = [s for s in pool if s not in prior]
    norms = []
    # 정의 마디 — 상한 밖의 별도 칸으로 뺀다(ReviewState.glossary). 회수한 법의
    # "용어의 뜻" 조 하나씩이고, 규범 6칸을 잡아먹지 않는다.
    picked = (prior + rest)[:limit]
    # ③′ 필수 동반을 **검색으로 찾은 조문에도** 건다 (2026-08-18 발견 — 그전엔
    #    문면 인용 좌표(prior)에만 걸려, 좌표 없는 구어 질문(B트랙)에선 배제·위임·
    #    수임·준용·제재 동반이 검토 경로에서 한 번도 안 돌았다). 동반은 상한 밖
    #    +4 까지, 정의는 여기서 빼고 아래 glossary 칸(호 단위)이 맡는다.
    picked = [x for x in expand_mod.expand_floor(idx, picked, cap=limit + 4)
              if x.kind != "정의" and not _is_deleted(x.text)]
    # 질의 스코프 보루 — 진입이 밖으로 샜으면 버리고 동반은 표식(scope_out).
    picked, _ = enforce_scope(idx, picked)
    used = {(x.doc_id, x.node) for x in picked}
    state.glossary += [x for x in _sibling_and_defn(idx, picked, cap=limit)
                       if x.kind == "정의" and not _is_deleted(x.text)
                       and (x.doc_id, x.node) not in used
                       and (x.doc_id, x.node) not in {(g.doc_id, g.node) for g in state.glossary}]
    for s in picked:
        v = idx.docs.get(s.doc_id)
        reqs = _reqs_from_nodes(v, s.doc_id, s.node) if v is not None else []
        if not reqs:                               # 마디가 비면 회수 본문으로 받는다
            body = re.sub(r"\s+", " ", s.text or "").strip()
            if not body:
                continue
            reqs = [Req(text=body[:REQ_STEM_CHARS], node=s.node,
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
        SUB_SCHEMA, max_tokens=int(control_value("review.subsume_output_tokens")),
        effort="low")
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
# 판정 입력은 **자르지 않는다** (2026-08-16 실측 15-0720): 정보공개법 제9조를 회수해
# 놓고 조당 700자로 잘라 넘기니 ①항 머리글에서 예산이 끝나 답이 있는 ①항 제5호가
# 빠졌다. 판정 모델은 정직하게 "그 조문 본문이 제시되지 않아 확정할 수 없다"고
# 조건부를 냈다 — 회수 채점은 2/2 성공인데 판정에는 답이 있는 부분이 안 갔다.
# 판정에는 회수한 조문의 **마디 전문**을 스토어에서 다시 읽어 준다. 규범 수 상한도
# 없앤다. 컨텍스트가 터지면 그때 좌표(질문이 인용한 항·호) 우선으로 배분한다.
_INTERP_NORMS_MAX = None     # 상한 없음
_INTERP_CHARS = None         # 자르지 않음 — 스토어 전문
# ── 판정 안정화 실측 (2026-08-16) ──────────────────────────────────────────
# 같은 state 로 판정 콜만 5회 반복(파이프라인 상류 고정):
#   하이쿠   16-0022 → 긍정2·조건부3 (같은 입력에 흔들림)   18-0261 → 긍정4·조건부1
#   소넷5    성공한 건 5/5 일치 — 단 max_tokens=600 이 사고 토큰에 먹혀 절반 넘게 잘림
# 4회차 뒤집힘 33%의 원인은 상류(쟁점 수·요건 수 분산은 뒤집힌 사례나 아닌 사례나
# 비슷)가 아니라 **판정 콜 자체의 분산**이었다. 표결 k=3 은 흔들리는 모델을 세 번
# 물은 것 — 비용 3배에 완화만 됐다. 흔들리지 않는 모델을 한 번 묻는 쪽이 맞다.
_INTERP_K = int(control_value("review.interpret_samples"))
_INTERP_MODEL = os.environ.get("REVIEW_INTERPRET_MODEL", "claude-sonnet-5")
_INTERP_MAX_TOKENS = int(control_value("review.interpret_output_tokens"))
                             # 출력 예산을 먹으므로 판정이 제일 잘 잘린다. 천장이라
                             # 안 쓰면 비용 0. 잘리면 llm.py 가 이름 붙여 보고
_CARD_CTX_CHARS = int(control_value("review.card_context_chars"))
_CARD_CTX_MAX = int(control_value("review.card_context_max"))
BASIS_MAX = int(control_value("review.basis_max"))
GLOSSARY_CONTEXT_MAX = int(control_value("review.glossary_context_max"))
UNMET_CONTEXT_MAX = int(control_value("review.unmet_context_max"))


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


def interpret_case(llm, st: ReviewState, idx=None) -> Optional[dict]:
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
    for n in uniq.values():
        # 요건표(Req.text)는 포섭용 조각(260/400자)이라 판정 입력으로 쓰면 잘린다.
        # 판정은 스토어의 마디 전문을 본다 — 조 아래 항·호·목까지 전부.
        body = ""
        v = idx.docs.get(n.doc_id) if idx is not None else None
        nd = v.by_id.get(n.node) if v is not None else None
        if nd is not None:
            body = v.section_text(nd, cap=10**9)
        if not body:
            body = " ".join(r.text for r in n.reqs)
        parts.append(f"◆ {n.doc} ▸ {n.path}\n{body}")
    # 용어 정의 — 규범과 섞지 않고 따로 싣는다. 판정이 "X가 Y에 해당하는가"를
    # 다룰 때 Y 의 정의가 없으면 답이 안 나온다(19-0152 는 정의 조가 정답이었다).
    defn_txt = ""
    if getattr(st, "glossary", None):
        rows = []
        for g in st.glossary[:GLOSSARY_CONTEXT_MAX]:
            gv = idx.docs.get(g.doc_id) if idx is not None else None
            gn = gv.by_id.get(g.node) if gv is not None else None
            rows.append(f"◆ {g.doc} ▸ {g.path}\n"
                        + (gv.section_text(gn, cap=8000) if gn is not None else g.text))
        defn_txt = "\n\n[용어 정의] (규범이 아니라 낱말의 뜻 — 해당성 판단에 쓴다)\n" \
                   + "\n\n".join(rows)
    unmet = [s for s in st.subs if s.judgment == "불충족"]
    unmet_txt = ("\n\n[포섭 관측 — 불충족 요건] (참고 — 핵심 요건인지 판정이 가린다)\n"
                 + "\n".join(f"- {s.req_text[:100]} ({s.reason[:60]})"
                             for s in unmet[:UNMET_CONTEXT_MAX])) if unmet else ""
    issues_txt = "\n".join(f"- {i.question}" + (f" (판단 축: {i.axis})" if i.axis
                                                else "") for i in st.issues)
    user = (f"[질문]\n{st.question[:2000]}\n\n[도출된 쟁점]\n{issues_txt}\n\n"
            f"[회수된 조문]\n" + "\n\n".join(parts) + defn_txt + unmet_txt
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
            "basis": [str(b)[:120] for b in lead.get("basis", [])][:BASIS_MAX],
            "votes": [v["direction"] for v in votes]}


# ---------------------------------------------------------------- 관통
# ====================================================================
# 회수 먼저, 쟁점은 뒤 (2026-08-18 재구조화)
#
# 옛 순서는 사실 → 쟁점(최대 4) → 쟁점마다 회수 6 → 포섭 이었다. 쟁점이
# **회수 단위**였고 그게 문제였다: (a) 쟁점 문장은 판단 축의 언어(심사)라
# 벡터를 엉뚱한 데로 보내고(18-0124: 정답 40위 밖), (b) 쟁점 3~4개가 각자
# 회수해 규범이 23~31개로 불어 판정이 흐려지며(2026-08-18 예시 4건: 회수는
# 6/12→10/12 올랐는데 판정 둘이 유보로 물러남), (c) 쟁점 재현율 41%가
# 회수 입력의 요동이 됐다. 오늘 회수를 올린 것들(원장 직행·정의어 호·법
# 스코프 깔때기·동반·probe)은 하나도 쟁점을 필요로 하지 않았다.
#
# 새 순서: 사실 → 재작성 1회 → **회수 1회**(검토 전체) → 회수된 조문을 **보고**
# 쟁점 판정 → 요건 → 포섭 → (부족하면 깔때기 1회) → 판정. 쟁점의 진짜 값은
# "무엇을 따질 것인가"(판정 골격·카드·판단 축)이고 그건 조문을 본 뒤가 제자리다
# — 질의응답 경로의 issue_spot_llm 이 이미 이 순서였고, 실무 순서이기도 하다.
# ====================================================================
REVIEW_NORMS = int(control_value("review.norms_total_max"))
PROBE_SYSTEM = (
    "너는 법령 검색용 질의 번역기다. 사용자 질문을 받아, 그 답이 될 조문이 **실제로 "
    "쓰였을 법한 문체**의 서술문 2개를 쓴다 — 하나는 조문 직역형, 하나는 핵심 "
    "주체·행위만 남긴 짧은 형. 규칙: 조문 문체('…할 수 있다'·'…하여야 한다'·"
    "'…요청할 수 있다'·'이 법 시행 당시') · 구어·질문형·심사 언어('해당하는가'·"
    "'명시되어 있는가'·'요건')는 쓰지 않는다 · 사안의 주체·행위를 조문의 낱말로 옮긴다"
    "(국세청→세무공무원, 넘겨줌→제공·협조 요청) · 법령명·조번호는 넣지 않는다 — "
    "지어내면 엉뚱한 데 착지한다."
)
PROBE_SCHEMA = {"type": "object",
                "properties": {"probes": {"type": "array", "items": {"type": "string"}}},
                "required": ["probes"], "additionalProperties": False}


def write_probes(llm, question: str) -> list:
    """재작성 1회 — 질문 → 조문 문체 1~2문장 (벡터 채널 전용). 실패면 빈 목록
    (호출부가 원문으로 폴백). 44마디 실측: probe 가 top1 을 두 배로 올린다."""
    if llm is None:
        return []
    out = llm.structured("review.probes", PROBE_SYSTEM, f"[질문]\n{question}",
                         PROBE_SCHEMA, max_tokens=PROBE_MAX_TOKENS, effort="low")
    if not out:
        return []
    return [str(x).strip()[:wikictx.PROBE_MAX_CHARS]
            for x in (out.get("probes") or [])[:ISSUE_PROBES_MAX]
            if str(x).strip()]


def _norms_from_sections(idx, secs: list, state: ReviewState) -> list:
    """구역 → Norm (요건은 마디에서). 상태에 누적."""
    out = []
    for s in secs:
        v = idx.docs.get(s.doc_id)
        reqs = _reqs_from_nodes(v, s.doc_id, s.node) if v is not None else []
        if not reqs:
            body = re.sub(r"\s+", " ", s.text or "").strip()
            if not body:
                continue
            reqs = [Req(text=body[:REQ_STEM_CHARS], node=s.node,
                        id=Req.coord_id(s.doc_id, s.node))]
        n = Norm(doc=s.doc, doc_id=s.doc_id, node=s.node, path=s.path,
                 reqs=reqs, effect="")
        out.append(n)
        state.norms.append(n)
    return out


def _query_definitions(idx, question: str, cap: int = 3) -> list:
    """질문에 쓰인 정의어 → 정의 호 (좌표 직행, 결정론). 긴 낱말 우선."""
    from lawrag.core.rag import definitions as definitions_mod
    from lawrag.core.rag.answer import SECTION_CHARS, Section
    pq = wikictx._pack(question)
    hits = []
    for did, v in idx.docs.items():
        for d in definitions_mod.defs(v):
            t = wikictx._pack(d["term"])
            if len(t) >= 3 and t in pq and d["scope"] == "doc":
                hits.append((did, d))
    hits.sort(key=lambda x: -len(x[1]["term"]))
    out, seen = [], set()
    for did, d in hits:
        if (did, d["node"]) in seen:
            continue
        seen.add((did, d["node"]))
        v = idx.docs[did]; dn = v.by_id.get(d["node"]) or {}
        out.append(Section(n=0, doc_id=did, doc=v.name, node=d["node"],
                           path=v.path(d["node"]) or v.name, page=dn.get("page"),
                           kind="정의", matched=f"질문의 '{d['term']}'",
                           text=v.section_outline(dn, cap=SECTION_CHARS) if dn else ""))
        if len(out) >= cap:
            break
    return out


def retrieve_once(idx, state: ReviewState, probes: list,
                  limit: int = REVIEW_NORMS, llm=None) -> list:
    """검토 전체에 **한 번** 회수한다 — 질문에서. 쟁점은 이 뒤에 온다.

    통로 (2026-08-18 회수 전략): ① 좌표 직행 — 문면 인용 · 원장 활성 · **용어집
    회수**(질문 → 용어 정확/이웃 → LLM 판별·조립 → 프레임 일치 조문, termretrieve)
    ② 검색으로 채움(벡터=probe, 어휘=원문) ③ 필수 동반(배제·위임·수임·준용·제재;
    정의는 호 단위로 glossary). 상한 limit(+동반 4). 용어집이 빈손이면 trail 에
    남기고 되먹임(깔때기)이 받는다."""
    q = state.question or ""
    coords = _cite_coords(idx, q) + promote_mod.direct_hits(q, index=idx)
    tcoords, tmeta = termretrieve_mod.retrieve(llm, idx, q)
    coords += tcoords
    state.step("용어집", len(tcoords),
               ("정확 " + " · ".join(tmeta.get("exact", [])[:5])
                + (" | 프레임 " + " / ".join(
                    "→".join(f.get(k, "") for k in ("actor", "act", "target", "object"))
                    for f in tmeta.get("frames", [])) if tmeta.get("frames") else f" | {tmeta.get('narrow', '')} → 메뉴 {tmeta.get('menu', 0)} → 선택 {len(tcoords)}"))[:160])
    prior = sections_from_coords(idx, coords) if coords else []
    prior = [s for s in prior if not _is_deleted(s.text)]
    have = {(s.doc_id, s.node) for s in prior}
    lex = [s for s in assemble(idx, run_search(idx, q))
           if not _is_deleted(s.text) and (s.doc_id, s.node) not in have]
    vqs = [p for p in (probes or []) if p] or [q]
    runs = [[s for s in _vector_sections(idx, vq, have, topk=limit * 2)
             if not _is_deleted(s.text)] for vq in vqs]
    vec = runs[0] if len(runs) == 1 else _interleave(runs[0], runs[1])
    pool = _interleave(vec, lex)
    picked = (prior + [s for s in pool if s not in prior])[:limit]
    picked = [x for x in expand_mod.expand_floor(idx, picked, cap=limit + 4)
              if x.kind != "정의" and not _is_deleted(x.text)]
    # 질의 스코프 보루 — 진입이 밖으로 샜으면 버리고 동반은 표식(scope_out).
    picked, _ = enforce_scope(idx, picked)
    used = {(x.doc_id, x.node) for x in picked}
    gl_have = {(g.doc_id, g.node) for g in state.glossary}
    for x in _query_definitions(idx, q) + _sibling_and_defn(idx, picked, cap=limit):
        if x.kind == "정의" and not _is_deleted(x.text) \
                and (x.doc_id, x.node) not in used and (x.doc_id, x.node) not in gl_have:
            gl_have.add((x.doc_id, x.node))
            state.glossary.append(x)
    return _norms_from_sections(idx, picked, state)


ISSUE_SYSTEM_AFTER = (
    ISSUE_SYSTEM[:ISSUE_SYSTEM.index("⑦ 쟁점마다 `조문질의`")].rstrip()
    + "\n⑦ [회수된 조문]이 함께 온다 — **조문을 읽고** 이 사안에 실제로 걸린 쟁점만 "
      "세운다(조문이 드러낸 준용·부칙·배제 구조가 쟁점이 되기도 한다). 쟁점마다 "
      "관련 조문의 번호를 norms 에 적는다(없으면 빈 배열 = 회수가 못 데려온 쟁점 — "
      "그것도 발견이다). 카드의 판단 축을 question·gate 에 베끼지 마라 — 사안의 말로 써라."
)
ISSUE_SCHEMA_AFTER = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {
        "type": "object",
        "properties": {"question": {"type": "string"}, "gate": {"type": "string"},
                       "card": {"type": "string"},
                       "regulation": {"type": "string", "enum": ["수평", "수직", "충돌", ""]},
                       "why": {"type": "string"},
                       "confidence": {"type": "string", "enum": ["핵심", "부수"]},
                       "norms": {"type": "array", "items": {"type": "integer"}}},
        "required": ["question", "gate", "card", "regulation", "why", "confidence", "norms"],
        "additionalProperties": False}}},
    "required": ["issues"], "additionalProperties": False,
}


def spot_issues_after(llm, facts: list, norms: list, limit: int = ISSUE_MAX) -> list:
    """② 쟁점 판정 — **회수된 조문을 보고** 세운다. LLM 이 없거나 빈손이면 트리거
    안전망(_issues_from_cards). 쟁점마다 참조한 규범 id 를 Issue.norms 에 단다
    (빈 목록이면 전부)."""
    rows = [r for r in wikictx._rows() if r["slug"].startswith("쟁점/")]
    if llm is None or not rows:
        return _issues_from_cards(facts, limit)
    menu = "\n".join(f"- {r['slug']} | {r['title']} | 판단 축: "
                     f"{wikictx._meta(r['text']).get('판단 축', '')}" for r in rows)
    fact_txt = "\n".join(f"- [{f.id}] {f.subject} / {f.action} / {f.object}"
                         f" ({f.tense}) — {f.text}" for f in facts)
    norm_txt = "\n".join(
        f"[{i}] {n.doc} ▸ {n.path.split(' ▸ ')[-1]} — "
        f"{re.sub(r'\s+', ' ', (n.reqs[0].text if n.reqs else ''))[:120]}"
        for i, n in enumerate(norms, start=1))
    user = (f"[정리된 사실]\n{fact_txt}\n\n[회수된 조문]\n{norm_txt}\n\n"
            f"[쟁점 카드 목록]\n{menu}")
    out = llm.structured("review.issues", ISSUE_SYSTEM_AFTER, user, ISSUE_SCHEMA_AFTER,
                         max_tokens=_ISSUE_MAX_TOKENS, effort="medium")
    if out is None or not out.get("issues"):
        log.info("쟁점(회수 후) 빈손 — 재시도")
        out = llm.structured("review.issues", ISSUE_SYSTEM_AFTER,
                             user + "\n\n[재시도] 조문에 규제 대상 행위가 있으면 반드시 쟁점을 세워라.",
                             ISSUE_SCHEMA_AFTER, max_tokens=_ISSUE_MAX_TOKENS, effort="medium")
    if out is None:
        return _issues_from_cards(facts, limit)
    by_slug = {r["slug"]: r for r in rows}
    issues = []
    for it in out.get("issues", [])[:limit]:
        row = by_slug.get(str(it.get("card") or "").strip())
        reg = str(it.get("regulation") or "") or None
        refs = [norms[i - 1].id for i in (it.get("norms") or [])
                if isinstance(i, int) and 1 <= i <= len(norms)]
        issues.append(Issue(
            question=str(it.get("question", ""))[:200], gate=str(it.get("gate", ""))[:200],
            axis=(wikictx._meta(row["text"]).get("판단 축", "") if row else ""),
            regulation=reg if reg in ("수평", "수직", "충돌") else None,
            card=row["slug"] if row else None, why=str(it.get("why", ""))[:300],
            core=(it.get("confidence") != "부수"), norms=refs))
    return issues or _issues_from_cards(facts, limit)


INADEQUATE_RATIO = float(control_value("review.inadequate_ratio"))
REFETCH_MAX = int(control_value("review.refetch_norms_max"))


def _inadequate(subs: list) -> bool:
    """포섭 결과가 '이거 아닌데'인가 — 판정된 요건이 있는데 거의 전부 불명·해당없음."""
    if not subs:
        return True
    off = sum(1 for x in subs if x.judgment in ("불명", "해당없음"))
    return off / len(subs) >= INADEQUATE_RATIO


def _refetch_by_funnel(llm, idx, issue: Issue, st: ReviewState,
                       exclude: list) -> list:
    """법 스코프 깔때기로 다시 찾아 규범을 보충한다 — 찾은 좌표는 승격 후보
    (잠정)로 원장에 적는다(사람 승인 뒤에야 다음 회수의 직행 좌표가 된다)."""
    from lawrag.core.rag import recover_domains, tuples as tuples_mod
    q = " ".join(x for x in (st.question, issue.question, issue.gate) if x)
    coords, meta = recover_domains.law_scoped_funnel(llm, idx, q)
    st.step("되먹임(깔때기)", len(coords), meta.get("note", ""))
    if not coords:
        return []
    have = {(n.doc_id, n.node) for n in exclude}
    secs = [x for x in sections_from_coords(idx, coords)
            if (x.doc_id, x.node) not in have and not _is_deleted(x.text)]
    out = []
    for x in secs[:REFETCH_MAX]:
        v = idx.docs.get(x.doc_id)
        reqs = _reqs_from_nodes(v, x.doc_id, x.node) if v is not None else []
        if not reqs:
            body = re.sub(r"\s+", " ", x.text or "").strip()
            if not body:
                continue
            reqs = [Req(text=body[:REQ_STEM_CHARS], node=x.node,
                        id=Req.coord_id(x.doc_id, x.node))]
        n = Norm(doc=x.doc, doc_id=x.doc_id, node=x.node, path=x.path,
                 reqs=reqs, effect="")
        out.append(n)
        st.norms.append(n)
        issue.norms.append(n.id)
    try:
        candidate_rows = [
            {"doc_id": n.doc_id, "node": n.node, "via": "법 스코프 깔때기",
             "card": issue.card or "", "issue": issue.question[:120]}
            for n in out
        ]
        from lawrag.core.rag import switches as switches_mod
        if switches_mod.is_on("sourceset_content_snapshot"):
            from lawrag.runtime.content_snapshot import current_content_snapshot

            snapshot = current_content_snapshot(required=True)
            assert snapshot is not None  # narrowed by required=True
            if getattr(idx, "content_snapshot_sha256", "") != (
                snapshot.content_snapshot_sha256
            ):
                candidate_rows = []
            else:
                receipt = snapshot.compact_receipt()
                bound_rows = []
                for row in candidate_rows:
                    view = idx.docs.get(row["doc_id"])
                    provenance = snapshot.provenance_for_document(row["doc_id"])
                    if view is None or view.content_provenance != provenance:
                        continue
                    bound_rows.append({
                        **row,
                        "content_snapshot": dict(receipt),
                        "content_provenance": provenance.receipt(),
                    })
                candidate_rows = bound_rows
        tuples_mod.record_candidates(st.question, candidate_rows)
    except Exception:                                    # pragma: no cover
        log.exception("깔때기 착지 원장 적재 실패 — 검토는 그대로 간다")
    return out


def run(llm, idx, text: str, track: str = "해석") -> ReviewState:
    """다섯 단계를 얇게 관통한다 — 상태 하나를 단계들이 갱신한다."""
    t0 = time.perf_counter()
    st = ReviewState(question=text, track=track)  # type: ignore[arg-type]

    st.facts = extract_facts(llm, text)
    st.step("사실 확정", len(st.facts),
            " · ".join(f"{f.subject}:{f.action}" for f in st.facts[:3]))

    # ② 재작성 1회 + 회수 1회 — 질문에서. 쟁점은 뒤다 (블록 머리).
    probes = write_probes(llm, text)
    all_norms = retrieve_once(idx, st, probes, llm=llm)
    st.step("회수", len(all_norms),
            (" · ".join(sorted({n.doc for n in all_norms}))[:70]
             + (f" · probe {len(probes)}" if probes else " · probe 없음(원문)")))
    if not all_norms:
        # 아무것도 못 찾았으면 법 스코프 깔때기를 여기서 한 번 (빈손 트리거)
        added = _refetch_by_funnel(llm, idx, Issue(question=text, gate=""), st,
                                   exclude=[]) if llm is not None else []
        all_norms = list(added)

    # ③ 쟁점 판정 — 회수된 조문을 보고
    st.issues = spot_issues_after(llm, st.facts, all_norms)
    st.step("쟁점 판정", len(st.issues),
            " · ".join(i.question[:28] for i in st.issues) or "걸린 쟁점 없음")
    if not st.issues:
        return st

    by_id = {n.id: n for n in all_norms}
    refetched = False                     # 되먹임은 검토당 1회 — 규범 팽창 방지
    for issue in st.issues:
        norms = [by_id[i] for i in issue.norms if i in by_id] or list(all_norms)
        subs = subsume(llm, issue, norms, st.facts)
        # 되먹임 — 포섭이 "이거 아닌데"면 법 스코프 깔때기로 직접 찾는다. 검토당
        # 한 번만: 쟁점마다 되돌면 규범이 30개로 불어 판정이 흐려진다(예시 4건 실측).
        if _inadequate(subs) and llm is not None and not refetched:
            refetched = True
            added = _refetch_by_funnel(llm, idx, issue, st, exclude=all_norms)
            if added:
                all_norms = all_norms + added
                by_id.update({n.id: n for n in added})
                subs = subs + subsume(llm, issue, added, st.facts)
                norms = norms + added
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
        st.overall = interpret_case(llm, st, idx)
        if st.overall:
            st.step("해석 판정", 1,
                    f"{st.overall['direction']} — {st.overall['reason'][:60]}")
    log.info("검토 완료 — 쟁점 %d, 요건 %d, 불명 %d (%.0fms)",
             len(st.issues), len(st.subs), len(st.unresolved()),
             (time.perf_counter() - t0) * 1000)
    return st
