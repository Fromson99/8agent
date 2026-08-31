"""회복 사다리의 도메인 단 — 범용 사다리 앞에 서는 "창고를 아는" 단들.

범용 회복 사다리(의미해석→깔때기→원문→수색대→둘러보기, recover.py)는
"구조를 모르는 문서 창고"용 브라우징이다. 그런데 도메인은 창고의 구조를
안다 — 법령판이라면 쟁점 카드가 조문 좌표를 알고(wikictx), 명칭 사전이
약칭("자본시장법")과 정식 명칭의 다리를 안다. 실측(2026-08-14)에서 범용
깔때기가 LLM 15콜·62초로 3구역을 찾는 동안 쟁점 재회수는 검색 1번으로
4구역을 데려왔다 — 아는 것을 앞단에 세우는 이유다.

등록부 계약:

    Rung.fn(llm, index, query) -> (coords, meta)
      coords = [{doc_id, node, via, why}]   # recover 의 좌표 모양 그대로
      meta   = {"note": str, ...}           # trail 관측용

- 도메인 단이 좌표를 찾으면 범용 사다리는 돌지 않는다 (첫-성공 규율 상속).
- 도메인 선택은 RAG_DOMAIN (기본 "law"). 다른 도메인(내규·사규·기술문서)은
  register() 로 단 목록만 등록하면 된다 — 범용 사다리는 그대로 물려받으므로
  등록할 게 없어도 동작은 오늘과 같다.
- 법령판 앞 두 단은 결정론(LLM 0콜)이다 — 회복은 이미 실패한 뒤의
  경로라, 여기서 또 지연을 얹지 않는다. 셋째 단(법 스코프 깔때기)만 LLM 을
  쓴다 — 어휘 격차는 결정론으로 못 넘고, 법을 알면 메뉴가 작아 2~3콜이다.
- 켜고 끄기는 사용자 몫 — 엔진 스위치 domain_recover (기본 켜짐).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from lawrag.core.rag import switches, wikictx
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index, store_path
from lawrag.core.rag.search import search as run_search

log = logging.getLogger("lawrag.core.rag.recover_domains")

COORDS_CAP = int(control_value("recover.domain_coords_max"))


@dataclass
class Rung:
    name: str                                    # trail 의 stage 이름 (한글)
    fn: Callable[[object, Index, str], tuple[list, dict]]


REGISTRY: dict[str, list[Rung]] = {}


def register(domain: str, name: str,
             fn: Callable[[object, Index, str], tuple[list, dict]]) -> None:
    REGISTRY.setdefault(domain, []).append(Rung(name=name, fn=fn))


def rungs(domain: Optional[str] = None) -> list[Rung]:
    return REGISTRY.get(domain or os.environ.get("RAG_DOMAIN", "law"), [])


# ---------------------------------------------------------------- 공통 조각
def _coords_from_search(index: Index, query: str, via: str, why: str) -> list:
    """확장 질의로 검색을 돌려 좌표만 뽑는다 — 결정론, 첫 CAP 개."""
    res = run_search(index, query)
    coords, seen = [], set()
    for h in res.hits:
        if h.node is None or not h.doc_id or (h.doc_id, h.node) in seen:
            continue
        seen.add((h.doc_id, h.node))
        coords.append({"doc_id": h.doc_id, "node": h.node, "via": via,
                       "why": why[:80]})
        if len(coords) >= COORDS_CAP:
            break
    return coords


# ---------------------------------------------------------------- 법령판 ①
def law_issue_respot(llm, index: Index, query: str) -> tuple[list, dict]:
    """쟁점 재회수 — 쟁점 카드가 서면 그 조문질의(probe)로 재검색한다.

    조문 후보(카드 좌표)는 질의에 넣지 않는다 — wikictx.expand_query 머리
    (2026-08-18 결정). 트리거 판은 probe 가 없으므로 이 단은 issue_spot_pre
    (LLM 재작성)가 켜져 있을 때만 실제로 선다.

    검색 전 확장(rag 라우터)과 같은 재료지만 자리가 다르다: 여기는 본
    검색·필터가 전멸한 뒤다. 라우터 쪽 확장이 이미 돌았어도, 필터가
    걸러낸 것과 다른 카드·다른 후보가 물릴 수 있어 다시 본다 (결정론이라
    비용은 검색 한 번이다).

    카드 고르기는 라우터의 검색 전 단과 **같은 판정기**를 쓴다 — 스위치
    issue_spot_pre 가 켜져 있으면 LLM 이 고르고(트리거 무매칭이어도 선다),
    꺼져 있거나 판정 불가면 트리거로 내려간다. 여기만 트리거로 남겨 두면
    앞단이 고친 오분류가 이 단에서 되살아난다(실측: '등록'이 물어 온
    「두 법의 관문」이 부칙 질문에 다시 붙었다).
    """
    spots = None
    if switches.is_on("issue_spot_pre"):
        spots = wikictx.spot_llm(llm, query)      # 컨텍스트 없음 = 검색 전 판
    if not spots:
        spots = wikictx.spot(query)
    if not spots:
        return [], {"note": "쟁점 무매칭"}
    qx = wikictx.expand_query(query, spots)
    if qx == query:
        return [], {"note": "조문질의 없음(트리거 판은 재작성이 없다)"}
    titles = " · ".join(s["title"] for s in spots)
    coords = _coords_from_search(index, qx, via="쟁점 재회수",
                                 why=f"카드 {titles}")
    return coords, {"note": titles, "cards": [s["slug"] for s in spots]}


# ---------------------------------------------------------------- 법령판 ②
def aliases_path() -> Path:
    return Path(os.environ.get("RAG_ALIASES",
                               store_path().parent / "aliases.json"))


def _load_aliases() -> dict[str, str]:
    p = aliases_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text("utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except Exception:                            # 깨진 사전은 없는 것으로 — 회복을 죽이지 않는다
        log.warning("명칭 사전 파싱 실패 — %s", p)
        return {}


def law_alias_expand(llm, index: Index, query: str) -> tuple[list, dict]:
    """명칭 확장 — 질문의 약칭("자본시장법")을 정식 명칭으로 펴서 재검색한다.

    검색 사다리 ①은 색인값(정식 명칭·용어)이 질의 **안에** 있는지를 보므로,
    약칭만 아는 질문은 정확 단을 놓친다. 사전(data/aliases.json — 법제처
    약칭 관행)이 그 다리다. 결정론·LLM 0콜.
    """
    aliases = _load_aliases()
    hits = [(a, full) for a, full in aliases.items()
            if a in query and full not in query]
    if not hits:
        return [], {"note": "약칭 없음"}
    qx = query + "\n[명칭 확장] " + " · ".join(full for _, full in hits)
    note = " · ".join(f"{a}→{full}" for a, full in hits[:3])
    coords = _coords_from_search(index, qx, via="명칭 확장", why=note)
    return coords, {"note": note, "expanded": [full for _, full in hits]}


# ---------------------------------------------------------------- 법령판 ③
def laws_named(index: Index, text: str) -> list[str]:
    """본문이 이름을 부른 코퍼스 문서 — 정식 명칭·축약(…에 관한 법률→…법)·
    약칭 사전(data/aliases.json) 세 갈래로 문다. 결정론."""
    import re as _re
    pq = wikictx._pack(text or "")
    def base(name: str) -> str:               # 업로드 문서는 확장자를 달고 있다
        return _re.sub(r"\.(pdf|xml|html?|docx?)$", "", name or "", flags=_re.I)
    keys: dict[str, str] = {}
    for did, v in index.entry_docs.items():          # 진입 — 스코프 안만
        nm = base(v.name)
        keys[wikictx._pack(nm)] = did
        keys.setdefault(wikictx._pack(nm.replace("에 관한 법률", "법")), did)
    by_name = {wikictx._pack(base(v.name)): did for did, v in index.entry_docs.items()}
    for a, full in _load_aliases().items():
        did = by_name.get(wikictx._pack(full))
        if did:
            keys.setdefault(wikictx._pack(a), did)
    out: list[str] = []
    # 긴 키부터 — "개인정보보호법시행령"이 "개인정보보호법"보다 먼저 물어야 시행령이 산다
    for k in sorted(keys, key=len, reverse=True):
        if len(k) >= 3 and k in pq and keys[k] not in out:
            out.append(keys[k])
    return out


def law_scoped_funnel(llm, index: Index, query: str) -> tuple[list, dict]:
    """법 스코프 깔때기 — 질문이 이름을 부른 법 **안에서만** 장→조를 내려가며
    읽고 고른다 (recover.rung_funnel 에 docs 를 좁혀 준 것).

    어휘 격차의 우회로다: 벡터는 "국세청이 개인정보를 받아가다"로 국세기본법
    제84조(세무공무원 … 협조를 요청)를 40위 밖에 두지만, 장 10개 → 조 15개의
    제목·첫머리를 **읽고 고르면** 낱말이 안 겹쳐도 닿는다(2026-08-18 실측:
    하이쿠 2콜에 제84조 3위 안). 코퍼스 전체에서 시작하는 범용 깔때기는
    15콜·62초였다 — 법을 알면 메뉴가 작아진다. 법령명이 없으면 **문서부터
    고른다**(pick_docs, 1콜) — 문서 → 장 → 조 균일 하강. LLM 이 없으면 침묵.
    """
    if llm is None:
        return [], {"note": "LLM 없음"}
    docs = laws_named(index, query)
    how = "이름"
    if not docs:
        # 법령명이 없으면 **문서부터 고른다** — 벡터 착지에 기대지 않고 문서 →
        # 장 → 조 균일한 구조 하강(2026-08-18 사용자 결정). 어느 법이 관할하는지는
        # 조문 낱말보다 일반 지식에 가까워 모델이 잘 고른다. 콜 하나가 더 든다.
        docs = pick_docs(llm, index, query)
        how = "선택"
        if not docs:
            return [], {"note": "법령명 없음 · 문서 선택도 빈손"}
    # 법마다 **따로** 내려간다 — 두 법의 장을 한 메뉴에 섞으면 질문 낱말이 많은
    # 쪽(개인정보 보호법)이 독식해 다른 법(국세기본법 제8장)이 안 열린다(실측).
    coords, notes = [], []
    for did in docs[:3]:
        c, dmeta = descend(llm, index, query, [did])
        coords += c
        notes.append(f"{index.docs[did].name[:14]} 장{dmeta.get('chapters', 0)}→조{dmeta.get('jos', 0)}→{len(c)}")
    return coords, {"note": f"({how}) " + " · ".join(notes), "laws": docs, "how": how}


# ---------------------------------------------------------------- 얇은 하강
# 범용 rung_funnel(recover.py)을 스코프만 좁혀 쓰면 걸음마다 nav+judge 콜이 나가
# 5걸음·십수 콜이고, 장·절 노드까지 좌표로 돌려준다(장이 규범이 되면 쓸모없다).
# 여기는 **두 콜**이다 — 장 고르기(제목만) → 조 고르기(제목 + 본문 첫머리) —
# 그리고 조만 돌려준다. 2026-08-18 실측: 18-0124 에서 이 모양이 제84조를 3위
# 안에 두었고, 범용 깔때기는 못 찾았다.
DESCEND_CHAPTERS = int(control_value("recover.chapters_max"))
DESCEND_JOS = int(control_value("recover.articles_per_chapter_max"))
_HEAD_CHARS = 90           # 조 메뉴의 본문 첫머리 — 제목만으론 "국세행정에 대한 협조"가 안 읽힌다
_JO_RE = None


def _jo_re():
    global _JO_RE
    if _JO_RE is None:
        import re as _re
        _JO_RE = _re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")
    return _JO_RE


def _chapters_of(v) -> list[dict]:
    """문서의 최상위 구획(장·편) — 부칙·별표 제외. 장이 없는 평면 문서면 뿌리 하나."""
    tops = [n for n in v.nodes if n.get("parent") is None
            and "부칙" not in (n.get("title") or n.get("surface") or "")
            and n.get("family") not in ("buchik", "annex")]
    return tops


def _jos_under(v, root_id) -> list[dict]:
    """구획 아래 조 전부 — 절·관을 뚫고 내려간다."""
    out, stack = [], [root_id]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for n in v.nodes:
            if n.get("parent") != cur:
                continue
            if _jo_re().fullmatch((n.get("surface") or "").strip()):
                out.append(n)
            elif not _jo_re().fullmatch((n.get("surface") or "").strip()):
                stack.append(n["id"])
    return out


_PICK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "why": {"type": "string"}},
        "required": ["id", "why"], "additionalProperties": False}}},
    "required": ["picks"], "additionalProperties": False,
}
_CH_SYSTEM = ("너는 법령 탐색기다. 질문의 답이 될 조문이 들어 있을 법한 **장**을 목록에서 "
              "고른다 — 최대 2개, 확신 순. 장 제목이 뭉툭해도('보칙'·'총칙') 그 안에 있을 "
              "수 있음을 염두에 둔다. 왜 골랐는지 한 줄.")
_JO_SYSTEM = ("너는 법령 탐색기다. 질문의 답이 될 조문을 목록(조 제목 + 본문 첫머리)에서 "
              "고른다 — 최대 3개, 확신 순. 낱말이 안 겹쳐도 **뜻이 같으면** 고른다(질문의 "
              "'받아간다'가 조문에선 '협조를 요청'일 수 있다). 왜 골랐는지 한 줄.")


def descend(llm, index: Index, query: str, doc_ids: list[str]) -> tuple[list, dict]:
    """문서들 안에서 장 → 조 두 콜 하강. 조 좌표만 돌려준다."""
    chapters = []
    for did in doc_ids:
        v = index.docs.get(did)
        if v is None:
            continue
        for c in _chapters_of(v):
            chapters.append((did, c))
    if not chapters:
        return [], {"chapters": 0, "jos": 0, "note": "구획 없음"}
    menu = "\n".join(f"- id={did}:{c['id']} | {index.docs[did].name} | "
                     f"{(c.get('surface') or '')} {(c.get('title') or '')[:40]}"
                     for did, c in chapters)
    out = llm.structured("rag.recover.descend.ch", _CH_SYSTEM,
                         f"[질문]\n{query}\n\n[장 목록]\n{menu}", _PICK_SCHEMA,
                         max_tokens=300, effort="low")
    if out is None:
        return [], {"chapters": len(chapters), "jos": 0, "note": "장 선택 실패"}
    valid = {f"{did}:{c['id']}": (did, c) for did, c in chapters}
    picked = [valid[p["id"]] for p in out.get("picks", []) if p.get("id") in valid][:DESCEND_CHAPTERS]
    if not picked:
        return [], {"chapters": len(chapters), "jos": 0, "note": "장 선택 빈손"}
    jos = []
    for did, c in picked:
        v = index.docs[did]
        for j in _jos_under(v, c["id"]):
            head = v.section_text(j, cap=200).replace("\n", " ")
            # 첫머리에서 "제N조(제목)" 머리는 떼고 본문만
            body = head.split(")", 1)[1].strip() if ")" in head[:60] else head
            jos.append((did, j, body[:_HEAD_CHARS]))
    if not jos:
        return [], {"chapters": len(chapters), "jos": 0, "note": "고른 장에 조 없음"}
    menu2 = "\n".join(f"- id={did}:{j['id']} | {j.get('surface','')} {(j.get('title') or '')[:30]} — {body}"
                      for did, j, body in jos)
    out2 = llm.structured("rag.recover.descend.jo", _JO_SYSTEM,
                          f"[질문]\n{query}\n\n[조 목록]\n{menu2}", _PICK_SCHEMA,
                          max_tokens=400, effort="low")
    if out2 is None:
        return [], {"chapters": len(chapters), "jos": len(jos), "note": "조 선택 실패"}
    valid2 = {f"{did}:{j['id']}": (did, j) for did, j, _ in jos}
    coords = []
    for p in out2.get("picks", [])[:DESCEND_JOS]:
        hit = valid2.get(p.get("id"))
        if hit:
            did, j = hit
            coords.append({"doc_id": did, "node": j["id"], "via": "법 스코프 깔때기",
                           "why": (p.get("why") or "")[:80]})
    return coords, {"chapters": len(chapters), "jos": len(jos),
                    "picked_chapters": [f"{index.docs[d].name[:10]} {c.get('surface','')}" for d, c in picked]}


PICK_DOCS_MAX = int(control_value("recover.documents_max"))
_PICK_DOCS_SYSTEM = (
    "너는 법령 탐색기다. 질문의 답이 될 조문이 들어 있을 법한 **문서**를 목록에서 "
    "고른다 — 최대 2개, 확신 순. 목록의 각 줄은 문서명·종별·제1조(목적)다. 상위법과 "
    "그 시행령이 둘 다 걸리면 둘 다 고른다. 확신이 없으면 빈 배열."
)
_PICK_DOCS_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "string"}},
                   "reason": {"type": "string"}},
    "required": ["picks", "reason"], "additionalProperties": False,
}


def _doc_purpose(v) -> str:
    """문서의 한 줄 — 제1조(목적) 본문 앞머리. 없으면 첫 조."""
    import re as _re
    for n in v.nodes:
        if _re.fullmatch(r"제1(?:-1)?조", (n.get("surface") or "").strip()):
            return v.section_text(n, cap=160).replace("\n", " ")
    return ""


def pick_docs(llm, index: Index, query: str, cap: int = PICK_DOCS_MAX) -> list[str]:
    """법령명이 없는 질문 → 문서 고르기 (LLM 1콜, 메뉴 = 문서명·목적)."""
    import json as _json
    rows = []
    for did, v in index.entry_docs.items():          # 메뉴는 스코프 안 문서만
        rows.append({"id": did, "문서": v.name, "목적": _doc_purpose(v)[:140]})
    out = llm.structured("rag.recover.pickdocs", _PICK_DOCS_SYSTEM,
                         f"[질문]\n{query}\n\n[문서 목록]\n"
                         + "\n".join(f"- id={r['id']} | {r['문서']} | {r['목적']}" for r in rows),
                         _PICK_DOCS_SCHEMA, max_tokens=300, effort="low")
    if out is None:
        return []
    ok = {r["id"] for r in rows}
    return [d for d in out.get("picks", []) if d in ok][:cap]


register("law", "쟁점 재회수", law_issue_respot)
register("law", "명칭 확장", law_alias_expand)
register("law", "법 스코프 깔때기", law_scoped_funnel)
