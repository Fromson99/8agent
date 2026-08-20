"""정의 용어 색인 — "이 문서에서 '개인정보처리자'는 제2조 5호가 정한다"를 낱말
단위로 미리 이어 둔 파생층. 결정론, LLM 없음.

정의 **조**를 통째로 동반하는 것(expand.floor_definition)은 방향은 맞았지만
거칠다 — 개보법 제17조가 오면 제2조의 호 열 개(영상정보처리기기까지)가 다
실려 모델이 그 안에서 스스로 찾아야 했다. 필요한 건 세 연결이다
(2026-08-18 사용자 결정 "문서에 있는 정의 단어들은 연결해야"):

    조문 → 쓰인 정의어의 **호**    회수 때 그 호만 동반 (컨텍스트 절약·정밀)
    질의 → 정의어의 호            사용자 낱말이 정의어면 좌표 직행
    판정 → 이 조문의 정의어 목록   요건 옆에 "이 낱말은 이렇게 정의됨"

재료는 다 있었다: 관할급 정의 조(tags.definition_jos, 관할 계산 포함) +
Tier1 정규식(정본 lawrag/core/defpatterns — 인용정의 `"X"란` · 이하별칭 `(이하 "X"라
한다)` · 정의문 `X이란 …를 말한다`) + 호 마디 좌표. 저자가 선언한 정의라
용어 사전의 승인 큐를 거치지 않는다(Tier1 이 정의 구획 안이면 high 로 두는
규율 그대로) — 다만 회수에선 **동반**으로만 쓰고 근거는 여전히 조문이다.

관할: 정의 조의 관할(문서 전체 / 편·장 / 조)은 tags 가 이미 아는 것을 따른다.
금융투자업규정처럼 편마다 정의 조가 있으면 제3편의 "운용"이 제8편 조문에
붙지 않는다. 별칭(이하 "법"이라 한다)은 문서 전체 관할이다.

저장: 없다 — DocView 위에 지연 계산·캐시(tags 와 같은 규율). 42문서 전량이
초 단위라 파일이 필요 없다.
"""
from __future__ import annotations

import re
from typing import Optional

from lawrag.core.rag import tags as tags_mod
from lawrag.core.defpatterns import RE_BARE, RE_QUOTED, RE_YIHA, _DEICTIC

_JO = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")
_INLINE_SCOPE = re.compile(r"이\s*(조|항|절|장|편)에서")   # 인라인 정의의 관할 선언
TERM_MAX = 40
COMPANION_MAX = 4          # 착지 하나가 동반하는 정의 호 상한 — 정의 조 통째보다 좁아야 뜻이 있다
_STOP = {"이 법", "이 영", "이 규정", "법", "영", "규정", "규칙", "세칙"}   # 별칭 중 문서 자기 지시는 뺀다


def _clean(term: str) -> str:
    t = re.sub(r"\s+", " ", term or "").strip(" \"“”‘’'")
    return t


_DOC_DECL = re.compile(r"이\s*(?:법|영|규정|규칙|세칙|고시|지침)에서")


def _jo_scope(v, jo: dict) -> tuple[str, Optional[int]]:
    """조 하나의 정의 관할 — 조 머리 본문의 선언이 정한다.
        "이 법/영/규정에서 …"      → ("doc", None)   문서 전체
        "이 편/장/절에서 …"        → ("sub", 그 조상)  그 구획
        선언 없는 관할급 정의 조   → 문서 첫 정의 조면 doc, 아니면 부모 구획
        그 밖(인라인 정의)         → ("jo", 조 id)   그 조 안
    """
    head = re.sub(r"\s+", " ", v.section_text(jo, cap=300) or "")
    m = _INLINE_SCOPE.search(head)
    if _DOC_DECL.search(head):
        return "doc", None
    if m:
        unit = m.group(1)
        if unit in ("조", "항"):
            return "jo", jo["id"]
        for a in tags_mod._chain(v, jo["id"])[1:]:
            if unit in (a.get("surface") or "") or (a.get("family") or "").endswith(unit):
                return "sub", a.get("id")
        return "doc", None
    djos = tags_mod.definition_jos(v)
    if jo["id"] in djos:
        if djos and jo["id"] == djos[0]:
            return "doc", None
        parent = jo.get("parent")
        return ("sub", parent) if parent is not None else ("doc", None)
    return "jo", jo["id"]


def _compute(v) -> list[dict]:
    cached = getattr(v, "_defs_cache", None)
    if cached is not None:
        return cached
    out: list[dict] = []
    seen: set[tuple] = set()

    def push(term: str, node_id: int, jo: dict, kind: str, scope, text: str):
        term = _clean(term)
        if not (1 < len(term) <= TERM_MAX) or term in _STOP:
            return
        if any(term.startswith(d) for d in _DEICTIC):
            return
        key = (term, node_id)
        if key in seen:
            return
        seen.add(key)
        sk, sroot = scope
        out.append({"term": term, "node": node_id, "jo": jo["id"],
                    "kind": kind, "scope": sk, "scope_root": sroot})

    jos = [n for n in v.nodes if _JO.fullmatch((n.get("surface") or "").strip())
           and "부칙" not in v.path(n["id"])]
    for jo in jos:
        scope = _jo_scope(v, jo)
        # 조의 자기 범위 안 마디들(항·호·목) — 정의가 실린 **가장 깊은** 마디를 좌표로
        s = jo.get("span") or [0, 0]
        for b in range(s[0], max(s[1], s[0] + 1)):
            blk = v.block_by_idx.get(b)
            if not blk:
                continue
            text = blk.get("text") or ""
            owner = v.owner(b) or jo
            node_id = owner.get("id", jo["id"])
            for m in RE_QUOTED.finditer(text):
                push(m.group(1), node_id, jo, "인용정의", scope, text)
            for m in RE_YIHA.finditer(text):
                push(m.group(3), node_id, jo, "별칭", ("doc", None), text)
            for m in RE_BARE.finditer(text):
                push(m.group(1), node_id, jo, "정의문", scope, text)
    v._defs_cache = out
    return out


# ---------------------------------------------------------------- 조회
def defs(v) -> list[dict]:
    """문서의 정의 용어 전부 — [{term, node, jo, kind, scope, scope_root}]."""
    return list(_compute(v))


def _in_scope(v, d: dict, node_id: int) -> bool:
    if d["scope"] == "doc":
        return True
    root = d["scope_root"]
    return any(a.get("id") == root for a in tags_mod._chain(v, node_id))


def terms_in(v, node_id: Optional[int], cap: int = COMPANION_MAX) -> list[dict]:
    """착지 마디 본문에 **쓰인** 정의어와 그 정의 호 — 관할 안의 것만, 긴 낱말 우선
    (더 구체적인 지목이 이긴다). 정의 마디 자신은 뺀다."""
    n = v.by_id.get(node_id) if node_id is not None else None
    if n is None:
        return []
    text = re.sub(r"\s+", "", v.section_text(n, cap=20000) or "")
    if not text:
        return []
    own = {a.get("id") for a in tags_mod._chain(v, node_id)}
    hits = []
    for d in _compute(v):
        if d["node"] in own or d["jo"] in own:
            continue                             # 자기 자신(정의 조 안)이면 동반 아님
        if re.sub(r"\s+", "", d["term"]) in text and _in_scope(v, d, node_id):
            hits.append(d)
    hits.sort(key=lambda d: -len(d["term"]))
    out, seen_nodes = [], set()
    for d in hits:
        if d["node"] in seen_nodes:
            continue
        seen_nodes.add(d["node"])
        out.append(d)
        if len(out) >= cap:
            break
    return out


def lookup(index, word: str) -> list[dict]:
    """낱말 → 그 낱말을 정의하는 (doc_id, node) 전부 — 질의 직행용."""
    w = re.sub(r"\s+", "", word or "")
    if len(w) < 2:
        return []
    out = []
    for did, v in index.entry_docs.items():          # 직행도 진입이다 — 스코프 안만
        for d in _compute(v):
            if re.sub(r"\s+", "", d["term"]) == w:
                out.append({"doc_id": did, "doc": v.name, **d})
    return out
