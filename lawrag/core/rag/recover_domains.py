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
- 법령판 두 단은 전부 결정론(LLM 0콜)이다 — 회복은 이미 실패한 뒤의
  경로라, 여기서 또 지연을 얹지 않는다. LLM 이 필요한 도메인 단이라면
  fn 이 받은 llm 을 쓰면 된다(없으면 None).
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
from lawrag.core.rag.index import Index, store_path
from lawrag.core.rag.search import search as run_search

log = logging.getLogger("lawrag.core.rag.recover_domains")

COORDS_CAP = 8              # 원문 단(FULLTEXT_CAP)과 같은 상한 — 회복은 보충이지 홍수가 아니다


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
    """쟁점 재회수 — 쟁점 카드의 트리거를 물면 조문 후보로 재검색한다.

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
        return [], {"note": "조문 후보 없음"}
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


register("law", "쟁점 재회수", law_issue_respot)
register("law", "명칭 확장", law_alias_expand)
