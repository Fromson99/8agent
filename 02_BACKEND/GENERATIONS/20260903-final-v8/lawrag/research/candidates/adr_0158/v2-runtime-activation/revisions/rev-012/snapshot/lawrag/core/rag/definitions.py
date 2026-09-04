"""정의 용어 색인 — "이 문서에서 '개인정보처리자'는 제2조 5호가 정한다"를 낱말
단위로 미리 이어 둔 파생층. 결정론, LLM 없음.

정의 **조**를 통째로 동반하는 것(expand.floor_definition)은 방향은 맞았지만
거칠다 — 개보법 제17조가 오면 제2조의 호 열 개(영상정보처리기기까지)가 다
실려 모델이 그 안에서 스스로 찾아야 했다. 필요한 건 네 연결이다
(2026-08-18 사용자 결정 "문서에 있는 정의 단어들은 연결해야"):

    조문 → 쓰인 정의어의 **호**    회수 때 그 호만 동반 (컨텍스트 절약·정밀)
    질의 → 정의어의 호            사용자 낱말이 정의어면 좌표 직행
    질의 A → 본문 속 B             `A(이하 B라 한다)`의 지역 검색어 확장
    판정 → 이 조문의 정의어 목록   요건 옆에 "이 낱말은 이렇게 정의됨"

재료는 다 있었다: 관할급 정의 조(tags.definition_jos, 관할 계산 포함) +
Tier1 정규식(정본 lawrag/core/defpatterns — 인용정의 `"X"란` · 이하별칭 `(이하 "X"라
한다)` · 정의문 `X이란 …를 말한다`) + 호 마디 좌표. 저자가 선언한 정의라
용어 사전의 승인 큐를 거치지 않는다(Tier1 이 정의 구획 안이면 high 로 두는
규율 그대로). `A → B`는 전역 동의어가 아니라 선언 문서 안에서, 선언 이후의
B 사용 좌표만 여는 방향성 검색 간선이다.

관할: 정의 조의 관할(문서 전체 / 편·장 / 조)은 tags 가 이미 아는 것을 따른다.
금융투자업규정처럼 편마다 정의 조가 있으면 제3편의 "운용"이 제8편 조문에
붙지 않는다. 별칭(이하 "법"이라 한다)은 문서 전체 관할이다.

저장: 없다 — DocView 위에 지연 계산·캐시(tags 와 같은 규율). 별칭 간선은
`이하`가 있는 블록만 선형 파싱하며, 실제 질의에서 일치한 A의 B 좌표만 연다.
"""
from __future__ import annotations

import re
from typing import Optional

from lawrag.core.rag import tags as tags_mod
from lawrag.core.defpatterns import RE_BARE, RE_QUOTED, RE_YIHA, _DEICTIC
from lawrag.core.rag.controls import value as control_value

_JO = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")
_INLINE_SCOPE = re.compile(r"이\s*(조|항|절|장|편)에서")   # 인라인 정의의 관할 선언
TERM_MAX = int(control_value("companion.terms_max"))
COMPANION_MAX = int(control_value("companion.definitions_per_term_max"))
_STOP = {"이 법", "이 영", "이 규정", "법", "영", "규정", "규칙", "세칙"}   # 별칭 중 문서 자기 지시는 뺀다
_DEFINITION_QUESTION = re.compile(r"(?:뜻|정의|무엇|뭐|이란|란\b|말하는|의미)")
_DEFINITION_TARGETS = (
    re.compile(
        r"([가-힣A-Za-z0-9·][가-힣A-Za-z0-9· ]{0,60}?)(?:의\s*)?"
        r"(?:뜻|정의|의미)(?:은|는|이|가)?"
    ),
    re.compile(
        r"([가-힣A-Za-z0-9·][가-힣A-Za-z0-9· ]{0,60}?)(?:이란|란)\s*"
    ),
)
_YIHA_TAIL = re.compile(
    r'이하\s*["“‘\']?([^\)"”’\']{1,25}?)["”’\']?\s*'
    r'(?:이?라\s*(?:한다|합니다|함))\s*\)'
)
_YIHA_PLAIN_HEAD = re.compile(
    r'([가-힣A-Za-z0-9·]+(?:\s+[가-힣A-Za-z0-9·]+){0,5})$'
)


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

    def push(term: str, node_id: int, jo: dict, kind: str, scope, text: str,
             block: Optional[int] = None):
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
                    "kind": kind, "scope": sk, "scope_root": sroot,
                    # 정의 부록은 조 전체가 아니라 실제 선언 블록을 그대로
                    # 보여 준다. 좌표·원문을 함께 저장한 지연 파생값일 뿐 별도
                    # canonical 데이터는 만들지 않는다.
                    "block": block, "source": str(text or "").strip()})

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
            # RE_YIHA는 긴 복합명사 열에서 ``이하``를 찾지 못할 때 역추적 비용이
            # 매우 크다. 실제 문법 표지가 없는 블록에는 정규식을 아예 실행하지
            # 않는다(대형 규정 한 문서 최초 접근 실측 12초의 대부분).
            if any(mark in text for mark in ('"', "“", "‘", "'")):
                for m in RE_QUOTED.finditer(text):
                    push(m.group(1), node_id, jo, "인용정의", scope, text, b)
            if "이하" in text:
                for m in RE_YIHA.finditer(text):
                    push(m.group(3), node_id, jo, "별칭", ("doc", None), text, b)
            if "이란" in text or "이라 함은" in text or "라 함은" in text:
                for m in RE_BARE.finditer(text):
                    push(m.group(1), node_id, jo, "정의문", scope, text, b)
    v._defs_cache = out
    return out


def _alias_edges(v) -> list[dict]:
    """``A(이하 B라 한다)``를 문서 범위 검색 간선 ``A → B``로 만든다.

    이 간선은 A와 B가 전역 동의어라는 주장이 아니다. 저자가 해당 문서의
    선언 이후에 B라고 쓰겠다는 지역 검색 규칙이다. 기존 ``defs``는
    정의 근거 좌표를 담당하고, 이 파생 간선은 질의 표면 확장만 담당한다.
    """
    cached = getattr(v, "_definition_alias_edges_cache", None)
    if cached is not None:
        return cached
    out, seen = [], set()
    for block in v.blocks:
        text = block.get("text") or ""
        if "이하" not in text:
            continue
        for marker in re.finditer("이하", text):
            # 긴 법조문 전체를 가변 길이 정규식에 넣지 않는다. '이하' 뒤와
            # 바로 앞 괄호를 각각 단방향으로 읽으면 같은 문법을 선형으로 얻는다.
            tail = _YIHA_TAIL.match(text, marker.start())
            open_paren = text.rfind("(", max(0, marker.start() - 120), marker.start())
            if tail is None or open_paren < 0 \
                    or text[open_paren + 1:marker.start()].strip():
                continue
            head = text[max(0, open_paren - 100):open_paren].rstrip()
            if head.endswith("」") and "「" in head:
                source = head.rsplit("「", 1)[1][:-1]
            else:
                head_match = _YIHA_PLAIN_HEAD.search(head)
                source = head_match.group(1) if head_match else ""
            source, target = _clean(source), _clean(tail.group(1))
            if len(re.sub(r"\s+", "", source)) < 2 or not target:
                continue
            if any(target.startswith(prefix) for prefix in _DEICTIC):
                continue
            # 구조화 block에는 이미 소속 node가 있다. 옛 산출물에 node가
            # 없을 때만 owner() 계층 탐색으로 폴백한다.
            owner = ({"id": block.get("node")} if block.get("node") is not None
                     else (v.owner(block.get("idx")) or {}))
            key = (source, target, block.get("idx"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "from": source, "to": target, "doc_id": v.doc_id,
                "doc": v.name, "node": owner.get("id"),
                "block": block.get("idx"), "scope": "doc-after-declaration",
            })
    v._definition_alias_edges_cache = out
    return out


# ---------------------------------------------------------------- 조회
def defs(v) -> list[dict]:
    """문서의 정의 용어 전부 — [{term, node, jo, kind, scope, scope_root}]."""
    return list(_compute(v))


def definition_root(v, node_id: Optional[int]) -> Optional[int]:
    """좌표가 속한 관할급 정의 조를 반환한다.

    LegalClosure는 모든 결과를 조 단위로 접지만 Assertion·참조 입력은 항·호 좌표일
    수 있다. 그래서 제목 문자열이 아니라 실제 정의 조 집합과 조상 사슬로 판별한다.
    """
    if node_id is None:
        return None
    roots = set(tags_mod.definition_jos(v))
    for node in tags_mod._chain(v, node_id):
        if node.get("id") in roots:
            return node.get("id")
    return None


def is_definition_node(v, node_id: Optional[int]) -> bool:
    """일반 지배규범 슬롯에서 분리할 정의 조(또는 그 자손)인가."""
    return definition_root(v, node_id) is not None


def context_entries(v, question: str, node_ids: list[int], *, cap: int = 3) \
        -> list[dict]:
    """선택 규정에서 실제로 필요한 정의만 원문 증명형 부록으로 만든다.

    질문 또는 최종 선택 조문에 정의어가 실제로 나타나고, 그 정의의 관할이 선택
    좌표 중 하나에 적용될 때만 싣는다. 정의 조 전체나 같은 문서의 모든 용어를 넣지
    않는다. 결과의 ``quote``는 정의 선언 블록의 공백만 정규화한 원문이다.
    """
    selected = [node_id for node_id in node_ids if node_id in v.by_id]
    if not selected or cap <= 0:
        return []
    q = re.sub(r"\s+", "", str(question or "")).casefold()
    selected_text = re.sub(
        r"\s+", "", "\n".join(v.section_text(v.by_id[node_id], cap=20000) or ""
                                  for node_id in selected)).casefold()
    rows = []
    for order, d in enumerate(_compute(v)):
        term_key = re.sub(r"\s+", "", d["term"]).casefold()
        question_hit = bool(term_key and term_key in q)
        provision_hit = bool(term_key and term_key in selected_text)
        if not (question_hit or provision_hit):
            continue
        if not any(_in_scope(v, d, node_id) for node_id in selected):
            continue
        quote = re.sub(r"\s+", " ", d.get("source") or "").strip()
        if not quote:
            node = v.by_id.get(d["node"])
            quote = re.sub(r"\s+", " ", v.section_text(node, cap=1200) or "").strip()
        if len(quote) > 600:
            quote = quote[:600].rstrip() + " …(원문 정의 블록 잘림)"
        rows.append({
            "term": d["term"], "kind": d["kind"],
            "doc_id": v.doc_id, "doc": v.name,
            "node": d["node"], "block": d.get("block"),
            "path": v.path(d["node"]) or v.name,
            "quote": quote,
            "matched_in": (["question"] if question_hit else [])
                          + (["selected_provision"] if provision_hit else []),
            "_provision_pos": selected_text.find(term_key) if provision_hit else -1,
            "_order": order,
        })
    # 질문에 저자 선언 용어가 하나라도 있으면 그 용어만 설명한다. 질문이 이미
    # 특정한 법정 용어를 두고 있는데 같은 조문의 다른 정의를 보태면 정확한
    # 부록이 다시 작은 용어집이 된다. 질문 hit가 전혀 없을 때만 최우선 조문에서
    # 쓰인 용어를 출현 순서대로 보충한다.
    if any("question" in row["matched_in"] for row in rows):
        rows = [row for row in rows if "question" in row["matched_in"]]
        rows.sort(key=lambda row: (-len(row["term"]), row["_order"]))
    else:
        rows.sort(key=lambda row: (row["_provision_pos"], -len(row["term"]),
                                   row["_order"]))
    out, seen = [], set()
    for row in rows:
        key = (row["term"], row["node"], row.get("block"))
        if key in seen:
            continue
        seen.add(key)
        row.pop("_order", None)
        row.pop("_provision_pos", None)
        out.append(row)
        if len(out) >= cap:
            break
    return out


def alias_edges(v) -> list[dict]:
    """저자 선언 별칭 간선 ``A → B`` 전부."""
    return list(_alias_edges(v))


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


def is_definition_question(question: str) -> bool:
    """용어의 뜻 자체를 묻는 질문인가. Assertion 사실 검색과 분리하는 게 목적이다."""
    return bool(_DEFINITION_QUESTION.search(str(question or "")))


def definition_target(question: str) -> str:
    """명시적인 ``X의 정의/뜻`` 질문에서 X의 실제 표면을 얻는다."""
    text = str(question or "").strip(" ?？.!。")
    for pattern in _DEFINITION_TARGETS:
        match = pattern.search(text)
        if match is None:
            continue
        target = _clean(match.group(1))
        # ``시험법에서 사업자의 정의``에서 문서 구조 앞부분은 이미 Document
        # 착지가 소비한다. 정의 대상은 마지막 ``에서`` 뒤의 표면이다.
        target = re.split(r"(?:에서는|에서의|에서)\s*", target)[-1].strip()
        return target
    return ""


def query_hits(index, question: str, *, doc_ids: set[str] | None = None) -> list[dict]:
    """질문에 통째로 들어 있는 저자 선언 정의어의 실제 정의 좌표.

    문서가 먼저 확정됐으면 그 문서의 원문 정의를 직접 훑는다. 문서가 없으면 이미
    컴파일된 활성 용어 색인의 ``via=정의`` 좌표를 사용해 전 문서 재계산을 피한다.
    ``금융투자업자``가 잡혔을 때 그 안의 ``금융투자업``은 더 긴 정의어가 이긴다.
    """
    qn = re.sub(r"\s+", "", str(question or "")).casefold()
    if not qn:
        return []
    rows: list[dict] = []
    if doc_ids:
        for did in sorted(doc_ids):
            v = index.entry_docs.get(did)
            if v is None:
                continue
            for d in _compute(v):
                key = re.sub(r"\s+", "", d["term"]).casefold()
                if len(key) >= 2 and key in qn:
                    rows.append({"doc_id": did, "doc": v.name, **d})
    else:
        for entry in index.entries:
            if entry.kind != "용어" or len(entry.key) < 2 or entry.key not in qn:
                continue
            for occurrence in entry.occurrences:
                if occurrence.get("via") != "정의" or occurrence.get("node") is None:
                    continue
                did = str(occurrence.get("doc_id") or "")
                if not did or not index.in_scope(did):
                    continue
                rows.append({
                    "doc_id": did, "doc": occurrence.get("doc") or
                    (index.docs.get(did).name if did in index.docs else did),
                    "term": entry.value, "node": occurrence["node"],
                    "jo": occurrence.get("jo") or occurrence["node"],
                    "kind": "정의", "scope": "doc", "scope_root": None,
                })

    keys = {re.sub(r"\s+", "", row["term"]).casefold() for row in rows}
    maximal = {key for key in keys
               if not any(key != other and key in other for other in keys)}
    out, seen = [], set()
    for row in sorted(rows, key=lambda item: (
            -len(re.sub(r"\s+", "", item["term"])), item["doc_id"],
            str(item["node"]))):
        key = re.sub(r"\s+", "", row["term"]).casefold()
        coordinate = (row["doc_id"], row["node"], key)
        if key not in maximal or coordinate in seen:
            continue
        seen.add(coordinate)
        out.append(row)
    return out


def _surface_in_text(surface: str, text: str) -> bool:
    """공백 표기 차이만 접어 별칭의 실제 사용을 찾는다."""
    return re.sub(r"\s+", "", surface).casefold() in \
        re.sub(r"\s+", "", text).casefold()


def query_expansion_hits(index, question: str, *,
                         doc_ids: set[str] | None = None,
                         coordinates: set[tuple] | None = None) -> list[dict]:
    """질문의 A를 문서 내 B 사용 좌표로 확장한 ``A → B`` 히트.

    정의 좌표 자체를 반환하는 ``query_hits``와 다르다. 여기서는
    A가 질문에 있고 B가 원문에 있는 경우, B가 쓰인 본문 좌표를
    찾는다. ``이하`` 선언은 미래 표기 규칙이므로 선언 블록 이후만 본다.
    원래 용어 A의 직접 출현과 B 출현은 교집합이 아니라 같은
    질문 조각의 대체 표면(OR)이다.
    """
    qn = re.sub(r"\s+", "", str(question or "")).casefold()
    if not qn:
        return []
    allowed = set(coordinates or ())
    docs = (sorted(doc_ids) if doc_ids else sorted(index.entry_docs))
    raw = []
    for doc_id in docs:
        view = index.entry_docs.get(doc_id)
        if view is None:
            continue
        # 문서 제목은 이미 Document 착지가 담당한다. ``자본시장법 → 법``
        # 같은 확장은 문서 전체의 '법'을 열어 의미가 없으므로 제외한다.
        doc_name = re.sub(r"\s+", "", view.name).casefold()
        for edge in _alias_edges(view):
            source_key = re.sub(r"\s+", "", edge["from"]).casefold()
            if source_key not in qn or source_key == doc_name:
                continue
            found = set()
            declaration_block = edge.get("block")
            for block in view.blocks:
                block_idx = block.get("idx")
                if isinstance(declaration_block, int) and isinstance(block_idx, int) \
                        and block_idx <= declaration_block:
                    continue
                if not _surface_in_text(edge["to"], block.get("text") or ""):
                    continue
                owner = ({"id": block.get("node")} if block.get("node") is not None
                         else (view.owner(block_idx) or {}))
                node = owner.get("id")
                pair = (doc_id, node)
                if node is None or (allowed and pair not in allowed):
                    continue
                found.add(pair)
            if found:
                raw.append({**edge, "coordinates": found})

    # '집합투자증권'이 잡혔으면 그 안의 '집합투자'는 별도 질문 조각으로
    # 보지 않는다. 같은 A가 여러 B로 정의된 경우만 좌표를 합친다.
    sources = {re.sub(r"\s+", "", row["from"]).casefold() for row in raw}
    maximal = {source for source in sources
               if not any(source != other and source in other for other in sources)}
    grouped: dict[tuple[str, str], dict] = {}
    for row in raw:
        source_key = re.sub(r"\s+", "", row["from"]).casefold()
        if source_key not in maximal:
            continue
        key = (row["doc_id"], source_key)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {**row, "targets": [row["to"]],
                            "coordinates": set(row["coordinates"])}
        else:
            if row["to"] not in existing["targets"]:
                existing["targets"].append(row["to"])
            existing["coordinates"].update(row["coordinates"])
    return sorted(grouped.values(), key=lambda row: (
        -len(re.sub(r"\s+", "", row["from"])), row["doc_id"], row["from"]))
