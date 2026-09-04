"""질문의 법률 대상을 시작점으로 삼는 구조적 전체본문 탐색 실험.

Concept 역매칭, BM25, Vector를 쓰지 않는다. LLM은 질문 원문을 법률 대상과
그 대상에 붙은 행위·조건으로만 나눈다. 전역에서는 대상만 검색하고, 대상이
나온 문서 안에서만 조건을 검색한다. 본문 시드를 고른 뒤에는 문서 트리의 인접
조문과 확정 참조 간선을 열어 다시 판정한다. 다중 검색어 교집합은 hard AND가
아니라 우선순위와 관측 신호다.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, replace

from lawrag.core.domain_graph import spanparts
from lawrag.core.rag import exploration, relations
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index


TERMS_MAX = 4
ANCHORS_MAX = 2
PAGE_SIZE = 12
PAGE_WINNERS_MAX = 2
DOCUMENTS_MAX = 3
SEEDS_MAX = 4
EXPANSIONS_MAX = 24
BODY_CHARS_MAX = 4000
EXCERPT_CHARS = 260
MANDATORY_RELATIONS = frozenset(relations.MANDATORY_KINDS)
_PACK = re.compile(r"[^0-9A-Za-z가-힣]+")
_NUMERIC_ONLY = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*[%A-Za-z가-힣]*\s*$")
_ARTICLE = re.compile(r"^제\s*\d+(?:-\d+)?조(?:의\s*\d+)?$")


def _pack(value: str) -> str:
    return _PACK.sub("", str(value or "")).casefold()


def _legal_phrase_key(value: str) -> str:
    """긴 법률 명사구에서 생략 가능한 관형격 조사 ``의``를 접은 보조 키."""
    packed = _pack(value)
    return packed.replace("의", "") if len(packed) >= 5 else packed


def _contains_legal_phrase(text: str, term: str) -> bool:
    packed_text, packed_term = _pack(text), _pack(term)
    if not packed_term:
        return False
    return (packed_term in packed_text
            or (len(packed_term) >= 5
                and _legal_phrase_key(term) in _legal_phrase_key(text)))


def packed(value: str) -> str:
    """법률 표면형 비교용 공백 제거·casefold 공개 API."""
    return _pack(value)


def contains_legal_phrase(text: str, term: str) -> bool:
    """조사 경계를 보존하는 법률 구문 일치 공개 API."""
    return _contains_legal_phrase(text, term)


_TERM_SYSTEM = (
    "너는 법률 원문 탐색을 위한 질문 분해기다. 질문에 실제로 적힌 연속 문자열만 "
    "사용하며 질문에 없는 동의어·법령명·조문·기관을 만들지 않는다. anchor_terms에는 "
    "법적 관계의 출발점이 되는 사람·조직·제도·권리·문서·대상 물건 같은 핵심 명사구를 "
    "최대 2개 넣는다. condition_terms에는 그 대상에 관하여 확인할 행위·상대방·자격·"
    "목적·시기·상태를 나타내는 질문 원문 구간을 넣는다. 일반적인 의문 표현과 숫자만인 "
    "표현은 제외한다. 긴 명사구 전체가 문서에 없을 때 사용할 더 짧은 독립 법률 대상 "
    "원문 구간만 fallback_terms에 넣는다. 세 배열을 합쳐 최대 4개다. "
    "operation_terms에는 사실관계의 일상 표현을 법령이 사용할 가능성이 높은 법적 업무유형·"
    "규율행위 명사구로 바꾼 표현을 최대 2개 넣을 수 있다. operation_terms는 질문 원문에 "
    "없어도 되지만 법령명·조문번호·기관을 만들지 말고, 행위의 법적 분류만 짧게 적는다. "
    "특정 사례의 정답을 추측하지 말고 문법적 역할과 법적 업무유형만 분해한다."
)
_TERM_SCHEMA = {
    "type": "object",
    "properties": {
        "anchor_terms": {"type": "array", "items": {"type": "string"}},
        "condition_terms": {"type": "array", "items": {"type": "string"}},
        "fallback_terms": {"type": "array", "items": {"type": "string"}},
        "operation_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["anchor_terms", "condition_terms", "fallback_terms", "operation_terms"],
    "additionalProperties": False,
}

_SELECT_SYSTEM = (
    "너는 질문 원문 용어가 실제로 출현한 문서 가지를 본문으로 판정한다. heading이나 "
    "matched_terms 개수만 보고 고르지 말고 body를 읽는다. 질문의 정의·자격·범위·"
    "적용대상 또는 직접 답을 규정하는 가지를 고른다. 용어가 우연히 등장하거나 "
    "서식·보고·제출 문맥에서 언급만 된 가지는 버린다. 본문에 없는 동일성이나 법률 "
    "관계를 추론하지 않는다. 새 법령·조문을 만들지 말고 입력된 O id만 반환하며, "
    "맞는 본문이 없으면 picks를 비운다."
)
_REVIEW_SYSTEM = (
    "너는 법률 조문 본문 검토자다. 후보에는 질문 용어로 찾은 seed와 그 seed에서 "
    "기계적으로 연 인접·참조 조문이 함께 있다. 모든 body를 읽고 질문의 직접 규율, "
    "원칙·예외·정의·필요한 연결 규정을 고른다. 검색어가 직접 없다는 이유만으로 관련 "
    "조문을 버리지 말고 origin과 relation_reason을 확인한다. 반대로 단순히 옆에 있거나 "
    "인용됐다는 이유만으로 고르지 않는다. 입력된 O id만 반환하고 근거가 없으면 비운다."
)
_DOCUMENT_SYSTEM = (
    "너는 법률 대상이 실제로 출현한 문서 중 질문을 규율할 문서를 고르는 탐색자다. "
    "matched_terms는 대상이 나온 문서 범위 안에서 추가 조건까지 검색한 결과다. 문서명만 "
    "보지 말고 source_kind, 시행·개정 메타, occurrence_examples의 경로와 원문을 읽는다. "
    "법적 권리·의무·자격 질문에서는 법령·규정의 직접 규율을 단순 서식·보고·제출 언급보다 "
    "우선 검토한다. 질문이 서식 자체를 묻는다면 서식을 고를 수 있다. 입력된 D id만 "
    "반환하며 맞는 문서가 없으면 picks를 비운다."
)


@dataclass(frozen=True)
class TermPlan:
    question: str
    anchor_terms: tuple[str, ...]
    condition_terms: tuple[str, ...]
    fallback_terms: tuple[str, ...]
    operation_terms: tuple[str, ...]
    rejected: tuple[str, ...]
    promoted_condition: bool = False

    @property
    def terms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            self.anchor_terms + self.condition_terms + self.operation_terms))


@dataclass(frozen=True)
class TermBranch:
    doc_id: str
    node: object
    doc: str
    path: str
    terms: tuple[str, ...]
    excerpts: tuple[str, ...]
    body: str
    body_chars: int
    origin: str = "exact"
    relation_reason: str = ""
    mandatory: bool = False
    mandatory_reason: str = ""
    # 관계 폐쇄로 온 조문의 출발 좌표. API scope의 밖으로 나갈 수 있는 것은
    # 이 좌표가 있는 동반뿐이며, answer.enforce_scope가 이를 검증한다.
    source_doc_id: str = ""
    source_node: object | None = None

    @property
    def coordinate(self) -> tuple[str, object]:
        return self.doc_id, self.node


def extract_terms(llm, question: str) -> TermPlan:
    """모델 분해 중 질문 원문에 실제로 포함된 구간만 통과시킨다."""
    q = str(question or "").strip()
    if not q or llm is None:
        return TermPlan(q, (), (), (), (), ())
    response = llm.structured(
        "rag.term_explore.extract", _TERM_SYSTEM, f"[질문]\n{q}",
        _TERM_SCHEMA, max_tokens=350, effort="low") or {}
    packed_question = _pack(q)
    rejected: list[str] = []

    def validate(values, seen: set[str], limit: int) -> list[str]:
        out = []
        for raw in values or ():
            value = re.sub(r"\s+", " ", str(raw or "")).strip()
            packed = _pack(value)
            if packed in seen:
                continue
            if (len(packed) < 2 or packed not in packed_question
                    or _NUMERIC_ONLY.fullmatch(value)):
                if value and value not in rejected:
                    rejected.append(value)
                continue
            seen.add(packed)
            out.append(value)
            if len(out) >= limit:
                break
        return out

    primary_seen: set[str] = set()
    anchors = validate(response.get("anchor_terms"), primary_seen, ANCHORS_MAX)
    conditions = validate(response.get("condition_terms"), primary_seen,
                          max(0, TERMS_MAX - len(anchors)))
    promoted = False
    if not anchors and conditions:
        anchors, conditions, promoted = conditions[:1], conditions[1:], True
    fallback_seen = set(primary_seen)
    fallbacks = validate(response.get("fallback_terms"), fallback_seen, TERMS_MAX)

    # operation은 질문 원문에 없는 법적 업무유형을 허용하는 유일한 필드다. 여기서는
    # 문법적 안전성만 검사하고, 실제 승격은 retrieve에서 코퍼스 정확 출현을 확인한 뒤다.
    operations, operation_seen = [], set()
    for raw in response.get("operation_terms") or ():
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        packed = _pack(value)
        if (len(packed) < 2 or packed in operation_seen
                or _NUMERIC_ONLY.fullmatch(value)
                or re.search(r"제\s*\d+조|법$|시행령$|시행규칙$", value)):
            if value and value not in rejected:
                rejected.append(value)
            continue
        operation_seen.add(packed)
        operations.append(value)
        if len(operations) >= ANCHORS_MAX:
            break
    return TermPlan(q, tuple(anchors), tuple(conditions), tuple(fallbacks),
                    tuple(operations), tuple(rejected), promoted)


def _excerpt(text: str, term: str) -> str:
    packed_term = _pack(term)
    if not packed_term:
        return text[:EXCERPT_CHARS]
    chars, positions = [], []
    for pos, char in enumerate(text):
        for value in _pack(char):
            chars.append(value)
            positions.append(pos)
    start = "".join(chars).find(packed_term)
    if start < 0:
        return text[:EXCERPT_CHARS]
    raw_start = positions[start]
    lo = max(0, raw_start - EXCERPT_CHARS // 3)
    return text[lo:min(len(text), lo + EXCERPT_CHARS)].strip()


def _branch(index: Index, doc_id: str, node: object,
            terms: tuple[str, ...], *, origin: str = "exact",
            relation_reason: str = "", excerpts: tuple[str, ...] = (),
            mandatory: bool = False, mandatory_reason: str = "") -> TermBranch:
    view = index.docs[doc_id]
    full = exploration.subtree_text(view, node, cap=None)
    matched = tuple(term for term in terms if _contains_legal_phrase(full, term))
    return TermBranch(
        doc_id=doc_id, node=node, doc=view.name,
        path=view.path(node) or view.name, terms=matched, excerpts=excerpts,
        body=full[:BODY_CHARS_MAX], body_chars=len(full), origin=origin,
        relation_reason=relation_reason, mandatory=mandatory,
        mandatory_reason=mandatory_reason)


def search_all(index: Index, terms: tuple[str, ...], *,
               doc_ids: set[str] | None = None) -> list[TermBranch]:
    """지정 문서 범위의 원문을 정확 검색하고 같은 선택 루트로 접는다."""
    grouped: dict[tuple[str, object], dict] = {}
    packed_terms = [(term, _pack(term)) for term in terms if _pack(term)]
    for doc_id, view in index.entry_docs.items():
        if doc_ids is not None and doc_id not in doc_ids:
            continue
        for block in view.blocks:
            text = str(block.get("text") or "")
            packed_text = _pack(text)
            matched = [term for term, packed in packed_terms
                       if packed in packed_text
                       or (len(packed) >= 5
                           and _legal_phrase_key(term) in _legal_phrase_key(text))]
            if not matched:
                continue
            owner = view.owner(block.get("idx"))
            if owner is None:
                continue
            root = exploration.selection_root(view, owner.get("id"))
            if root not in view.by_id:
                continue
            row = grouped.setdefault((doc_id, root), {"terms": [], "excerpts": []})
            for term in matched:
                if term not in row["terms"]:
                    row["terms"].append(term)
                excerpt = _excerpt(text, term)
                if excerpt and excerpt not in row["excerpts"]:
                    row["excerpts"].append(excerpt)
    out = [_branch(index, doc_id, node, tuple(terms),
                   excerpts=tuple(row["excerpts"][:3]))
           for (doc_id, node), row in grouped.items()]
    return sorted(out, key=lambda row: (
        -len(row.terms), row.doc, row.path, str(row.node)))


def _choose_page(llm, question: str, branches: list[TermBranch], *, level: str,
                 keep: int, audit: list[dict], review: bool = False) -> list[TermBranch]:
    ids = [f"O{pos}" for pos in range(1, len(branches) + 1)]
    public = [{
        "id": oid, "document": row.doc, "path": row.path,
        "matched_terms": list(row.terms), "excerpts": list(row.excerpts),
        "origin": row.origin, "relation_reason": row.relation_reason,
        "mandatory": row.mandatory,
        "mandatory_reason": row.mandatory_reason,
        "body": row.body, "body_chars": row.body_chars,
        "body_complete": len(row.body) == row.body_chars,
    } for oid, row in zip(ids, branches)]
    schema = {
        "type": "object",
        "properties": {
            "picks": {"type": "array", "items": {"type": "string", "enum": ids}},
            "reason": {"type": "string"},
        },
        "required": ["picks", "reason"], "additionalProperties": False,
    }
    response = llm.structured(
        f"rag.term_explore.{'review' if review else 'select'}.{level}",
        _REVIEW_SYSTEM if review else _SELECT_SYSTEM,
        f"[질문]\n{question}\n\n[선택 상한]\n{keep}\n\n[본문 후보]\n"
        f"{json.dumps(public, ensure_ascii=False, indent=1)}",
        schema, max_tokens=900, effort="low") or {}
    allowed = {oid: row for oid, row in zip(ids, branches)}
    picks = list(dict.fromkeys(
        oid for oid in response.get("picks") or () if oid in allowed))[:keep]
    audit.append({
        "level": f"{'review' if review else 'select'}.{level}",
        "option_count": len(branches), "picks": picks,
        "reason": str(response.get("reason") or ""),
        "options": [{
            "id": oid, "document": row.doc, "path": row.path,
            "terms": list(row.terms), "origin": row.origin,
            "relation_reason": row.relation_reason, "body_chars": row.body_chars,
            "mandatory": row.mandatory,
            "mandatory_reason": row.mandatory_reason,
        } for oid, row in zip(ids, branches)],
    })
    return [allowed[oid] for oid in picks]


def _authority_rank(index: Index, doc_id: str) -> int:
    view = index.docs[doc_id]
    return 2 if view.scope_kind == "서식" else 1 if view.scope_kind == "내규" else 0


def _document_groups(index: Index, branches: list[TermBranch]) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in branches:
        view = index.docs[row.doc_id]
        group = groups.setdefault(row.doc_id, {
            "doc_id": row.doc_id, "doc": row.doc, "terms": [], "branches": [],
            "source_kind": view.kind, "scope_kind": view.scope_kind,
            "enforce": view.enforce, "revised": view.revised,
            "authority_rank": _authority_rank(index, row.doc_id),
        })
        group["branches"].append(row)
        for term in row.terms:
            if term not in group["terms"]:
                group["terms"].append(term)
    return sorted(groups.values(), key=lambda row: (
        -len(row["terms"]), row["authority_rank"], row["doc"], row["doc_id"]))


def _choose_document_page(llm, question: str, groups: list[dict], *,
                          level: str, keep: int, audit: list[dict]) -> list[dict]:
    ids = [f"D{pos}" for pos in range(1, len(groups) + 1)]
    public = []
    for oid, group in zip(ids, groups):
        examples = [{
            "path": row.path, "matched_terms": list(row.terms),
            "text": row.excerpts[0] if row.excerpts else row.body[:EXCERPT_CHARS],
        } for row in group["branches"][:8]]
        public.append({
            "id": oid, "document": group["doc"],
            "source_kind": group["source_kind"], "scope_kind": group["scope_kind"],
            "enforce": group["enforce"], "revised": group["revised"],
            "matched_terms": list(group["terms"]),
            "occurrence_branches": len(group["branches"]),
            "occurrence_examples": examples,
        })
    schema = {
        "type": "object",
        "properties": {
            "picks": {"type": "array", "items": {"type": "string", "enum": ids}},
            "reason": {"type": "string"},
        },
        "required": ["picks", "reason"], "additionalProperties": False,
    }
    response = llm.structured(
        f"rag.term_explore.document.{level}", _DOCUMENT_SYSTEM,
        f"[질문]\n{question}\n\n[선택 상한]\n{keep}\n\n"
        f"[대상어 출현 문서 안의 조건 검색 결과]\n"
        f"{json.dumps(public, ensure_ascii=False, indent=1)}",
        schema, max_tokens=750, effort="low") or {}
    allowed = {oid: row for oid, row in zip(ids, groups)}
    picks = list(dict.fromkeys(
        oid for oid in response.get("picks") or () if oid in allowed))[:keep]
    audit.append({
        "level": f"document.{level}", "option_count": len(groups),
        "picks": picks, "reason": str(response.get("reason") or ""),
        "options": [{
            "id": oid, "document": row["doc"], "terms": list(row["terms"]),
            "source_kind": row["source_kind"], "branches": len(row["branches"]),
        } for oid, row in zip(ids, groups)],
    })
    return [allowed[oid] for oid in picks]


def _select_documents(index: Index, llm, question: str,
                      branches: list[TermBranch], *, audit: list[dict]) -> list[dict]:
    current = _document_groups(index, branches)
    round_no = 1
    while len(current) > PAGE_SIZE:
        winners = []
        for pos in range(0, len(current), PAGE_SIZE):
            winners.extend(_choose_document_page(
                llm, question, current[pos:pos + PAGE_SIZE],
                level=f"round{round_no}.page{pos // PAGE_SIZE + 1}",
                keep=PAGE_WINNERS_MAX, audit=audit))
        if not winners or len(winners) >= len(current):
            current = winners
            break
        current = winners
        round_no += 1
    return (_choose_document_page(
        llm, question, current, level="final", keep=DOCUMENTS_MAX, audit=audit)
        if current else [])


def _select_from_pages(llm, question: str, branches: list[TermBranch], *, cap: int,
                       audit: list[dict], stage: str,
                       review: bool = False) -> list[TermBranch]:
    current = list(branches)
    round_no = 1
    while len(current) > PAGE_SIZE:
        winners = []
        for pos in range(0, len(current), PAGE_SIZE):
            winners.extend(_choose_page(
                llm, question, current[pos:pos + PAGE_SIZE],
                level=f"{stage}.round{round_no}.page{pos // PAGE_SIZE + 1}",
                keep=PAGE_WINNERS_MAX, audit=audit, review=review))
        if not winners or len(winners) >= len(current):
            current = winners
            break
        current = winners
        round_no += 1
    return (_choose_page(
        llm, question, current, level=f"{stage}.final", keep=max(1, int(cap)),
        audit=audit, review=review) if current else [])


def _contains_node(view, root: object, node: object) -> bool:
    r, n = view.by_id.get(root), view.by_id.get(node)
    if r is None or n is None:
        return False
    rs, ns = r.get("span") or [0, 0], n.get("span") or [0, 0]
    return rs[0] <= ns[0] < max(rs[1], rs[0] + 1)


def _article_root(view, node: object) -> object:
    cur = view.by_id.get(node)
    seen = set()
    while cur is not None and cur.get("id") not in seen:
        seen.add(cur.get("id"))
        if _ARTICLE.fullmatch(str(cur.get("surface") or "").strip()):
            return cur.get("id")
        cur = view.by_id.get(cur.get("parent"))
    return node


def article_root(view, node: object) -> object:
    """임의 구조 node가 속한 조문 root를 반환하는 공개 API."""
    return _article_root(view, node)


def explicit_structure_seeds(index: Index, question: str,
                             terms: tuple[str, ...]) -> tuple[list[TermBranch], dict]:
    """질문에 명시된 문서·조문 좌표를 검색 결과와 무관하게 필수 seed로 연다.

    명시 주소는 다른 문서를 막는 hard scope가 아니라 관계 탐색의 출발점이다.
    ``resolve_structure``가 조문의 모든 자손 좌표를 돌려주므로 조 단위로 접어
    중복 없이 보존한다. 문서명만 있고 조문이 없으면 문서 전체를 seed로 만들지
    않는다. 그 경우에는 기존 대상어 문서 선택이 정밀도를 담당한다.
    """
    anchors = spanparts.resolve_structure(index, question)
    seeds: list[TermBranch] = []
    seen: set[tuple[str, object]] = set()
    for doc_id, node in anchors.source_coordinates:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        root = _article_root(view, node)
        key = (doc_id, root)
        if key in seen:
            continue
        seen.add(key)
        seeds.append(_branch(
            index, doc_id, root, terms, origin="explicit-coordinate",
            relation_reason="질문에 명시된 법령·조문 좌표",
            mandatory=True, mandatory_reason="explicit-coordinate"))
    return seeds, {
        "documents": list(anchors.documents),
        "locators": list(anchors.locators),
        "unresolved_locators": list(anchors.unresolved_locators),
        "seed_count": len(seeds),
    }


def expand_structural(index: Index, seeds: list[TermBranch],
                      terms: tuple[str, ...], *, cap: int = EXPANSIONS_MAX) \
        -> tuple[list[TermBranch], dict]:
    """seed에서 인접 조문과 확정 참조 간선을 결정론적으로 한 층 연다."""
    seed_coords = {row.coordinate for row in seeds}
    expanded: dict[tuple[str, object], TermBranch] = {}
    events: list[dict] = []

    def push(doc_id: str, node: object, origin: str, reason: str, *,
             relation: str = "") -> None:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id or len(expanded) >= cap:
            return
        root = exploration.selection_root(view, node)
        if (doc_id, root) in seed_coords or (doc_id, root) in expanded:
            return
        mandatory = relation in MANDATORY_RELATIONS
        row = _branch(
            index, doc_id, root, terms, origin=origin, relation_reason=reason,
            mandatory=mandatory,
            mandatory_reason=(f"relation:{relation}" if mandatory else ""))
        expanded[(doc_id, root)] = row
        events.append({"doc_id": doc_id, "node": root, "doc": row.doc,
                       "path": row.path, "origin": origin, "reason": reason,
                       "relation": relation, "mandatory": mandatory})

    # 본문 인용·공식 위임·정의 적용·제재·시점 관계를 같은 인접 리스트로 걷는다.
    # 여기서 별도 source별 로더를 부르면 그래프 빌더와 제품 검색의 관계 집합이 다시
    # 갈라지므로, 모든 section 관계는 relations 모듈만 통과한다.
    for seed in seeds:
        view = index.docs[seed.doc_id]
        article = relations.article_root(view, seed.node)
        outgoing, incoming = relations.incident(index, seed.doc_id, article)
        for edge in outgoing:
            push(edge.dst_doc, edge.dst_node,
                 f"relation:outgoing:{edge.kind}",
                 f"{seed.path} → {edge.explanation()}", relation=edge.kind)
        for edge in incoming:
            push(edge.src_doc, edge.src_node,
                 f"relation:incoming:{edge.kind}",
                 f"{edge.explanation(reverse=True)} → {seed.path}", relation=edge.kind)

    for seed in seeds:
        view = index.docs[seed.doc_id]
        article = _article_root(view, seed.node)
        node = view.by_id.get(article)
        if node is None:
            continue
        siblings = [n for n in view.nodes
                    if n.get("parent") == node.get("parent")
                    and _ARTICLE.fullmatch(str(n.get("surface") or "").strip())]
        try:
            pos = next(i for i, n in enumerate(siblings) if n.get("id") == article)
        except StopIteration:
            continue
        if pos > 0:
            push(seed.doc_id, siblings[pos - 1].get("id"), "neighbor:previous",
                 f"{seed.path}의 바로 앞 조문")
        if pos + 1 < len(siblings):
            push(seed.doc_id, siblings[pos + 1].get("id"), "neighbor:next",
                 f"{seed.path}의 바로 뒤 조문")

    return list(expanded.values()), {
        "seed_count": len(seeds), "expanded_count": len(expanded),
        "cap": cap, "events": events,
    }


def _intersection(branches: list[TermBranch], terms: tuple[str, ...]) -> dict:
    counts = Counter(len(set(row.terms)) for row in branches)
    combos = Counter(tuple(term for term in terms if term in set(row.terms))
                     for row in branches)
    return {
        "terms": list(terms),
        "coverage": {str(n): counts[n] for n in sorted(counts)},
        "combinations": [{"terms": list(combo), "branches": count}
                         for combo, count in sorted(
                             combos.items(),
                             key=lambda item: (-len(item[0]), -item[1], item[0]))],
        "all_terms": counts.get(len(terms), 0) if terms else 0,
        "two_or_more": sum(count for n, count in counts.items() if n >= 2),
    }


def retrieve(index: Index, question: str, *, llm, cap: int = 4) \
        -> tuple[list[Section], dict]:
    """대상 anchor→문서 내 조건→seed→구조 확장→본문 재검토."""
    started = time.perf_counter()
    # 공식 법령 개정본을 보존하더라도 일반 질의의 진입점은 현행본뿐이다.
    # 신구 비교는 호출부가 구판 스코프를 명시해 여는 별도 경로다.
    # 호출부가 사용자 scope를 이미 씌웠다면 그대로 보존한다. scoped(None)을
    # 다시 부르면 기본 현행 범위로 넓어져 API의 "이 문서들만" 계약을 깬다.
    index = index if index.scope is not None else index.scoped(None)
    plan = extract_terms(llm, question)
    used_anchors = plan.anchor_terms
    anchor_branches = search_all(index, used_anchors)
    used_fallback = False
    if not anchor_branches and plan.fallback_terms:
        used_anchors = plan.fallback_terms
        anchor_branches = search_all(index, used_anchors)
        used_fallback = True

    # 일상 사실관계 → 법적 업무유형 변환은 모델의 말만으로 seed가 되지 않는다.
    # 실제 코퍼스 본문에 정확히 존재하는 제안만 통과시키고, 이후 문서·본문 선택도
    # 원래의 닫힌 후보 메뉴를 그대로 거친다.
    operation_branches = search_all(index, plan.operation_terms)
    operation_hits = {term for row in operation_branches for term in row.terms}
    grounded_operations = tuple(
        term for term in plan.operation_terms if term in operation_hits)
    operation_branches = [row for row in operation_branches
                          if set(row.terms).intersection(grounded_operations)]

    audit: list[dict] = []
    # fallback은 전역 문서를 새로 열지 않는다. anchor가 잡은 문서 안에서만 긴
    # 조건구의 표현 불일치를 더 짧은 질문 원문 구간으로 보완한다.
    scoped_fallbacks = (() if used_fallback else plan.fallback_terms)
    all_terms = tuple(dict.fromkeys(
        used_anchors + plan.condition_terms + scoped_fallbacks
        + grounded_operations))
    used_fallback = used_fallback or bool(scoped_fallbacks)
    explicit_seeds, structure_meta = explicit_structure_seeds(
        index, question, all_terms)
    anchor_doc_ids = {row.doc_id for row in [*anchor_branches, *operation_branches]}
    routed_branches = (search_all(index, all_terms, doc_ids=anchor_doc_ids)
                       if anchor_doc_ids else [])
    documents = (_select_documents(
        index, llm, question, routed_branches, audit=audit)
        if routed_branches else [])
    selected_doc_ids = {row["doc_id"] for row in documents}
    # 문서를 고른 뒤에도 seed 가지에는 anchor가 반드시 하나 이상 있어야 한다.
    # 조건어(예: '처분')만 나온 같은 문서의 모든 조문을 다시 열면 문서 범위 축소가
    # 무력화된다. 조건은 anchor 가지의 교집합 우선순위로만 작동한다.
    anchor_set = set((*used_anchors, *grounded_operations))
    document_scoped = [row for row in routed_branches
                       if row.doc_id in selected_doc_ids]
    scoped = [row for row in document_scoped
              if anchor_set.intersection(row.terms)]
    intersected = [row for row in scoped if len(set(row.terms)) >= 2]
    seed_pool = intersected or scoped
    seed_mode = "two-or-more" if intersected else "anchor-relaxed"
    term_seeds = (_select_from_pages(
        llm, question, seed_pool, cap=SEEDS_MAX, audit=audit, stage="seed")
        if seed_pool else [])
    # seed 선택을 이미 통과한 정확 본문과 사용자가 명시한 좌표는 최종 본문
    # 검토자가 다시 삭제하지 못한다. 명시 좌표는 먼저 두되 좌표 중복은 접는다.
    seeds: list[TermBranch] = []
    seed_seen: set[tuple[str, object]] = set()
    for row in [*explicit_seeds, *term_seeds]:
        if row.coordinate in seed_seen:
            continue
        seed_seen.add(row.coordinate)
        seeds.append(row if row.mandatory else replace(
            row, mandatory=True, mandatory_reason="selected-exact-seed"))
    expanded, expansion_meta = expand_structural(index, seeds, all_terms)
    review_candidates = seeds + expanded
    mandatory = []
    mandatory_seen: set[tuple[str, object]] = set()
    for row in review_candidates:
        if not row.mandatory or row.coordinate in mandatory_seen:
            continue
        mandatory_seen.add(row.coordinate)
        mandatory.append(row)
    optional = [row for row in review_candidates if not row.mandatory]
    optional_slots = max(0, int(cap) - len(mandatory))
    optional_selected = (_select_from_pages(
        llm, question, optional, cap=optional_slots, audit=audit,
        stage="body", review=True) if optional and optional_slots else [])
    selected = (mandatory + optional_selected)[:max(1, int(cap))]

    sections = [Section(
        n=0, doc_id=row.doc_id, doc=row.doc, node=row.node,
        path=row.path, page=index.docs[row.doc_id].by_id[row.node].get("page"),
        kind="구조적용어탐색",
        matched=(("정확용어 — " + " · ".join(row.terms)) if row.terms
                 else row.relation_reason),
        text=exploration.subtree_text(index.docs[row.doc_id], row.node, cap=None),
    ) for row in selected]
    meta = {
        "strategy": "anchor_scoped_intersection_structural_expansion",
        "embedding": False, "bm25": False, "concept_reverse_match": False,
        "term_plan": {
            "anchor_terms": list(plan.anchor_terms),
            "condition_terms": list(plan.condition_terms),
            "terms": list(plan.terms), "fallback_terms": list(plan.fallback_terms),
            "operation_terms": list(plan.operation_terms),
            "grounded_operation_terms": list(grounded_operations),
            "rejected_operation_terms": [term for term in plan.operation_terms
                                          if term not in operation_hits],
            "used_anchor_terms": list(used_anchors), "used_terms": list(all_terms),
            "used_fallback": used_fallback,
            "promoted_condition": plan.promoted_condition,
            "rejected": list(plan.rejected),
        },
        "anchor_candidate_branches": len(anchor_branches),
        "semantic_operation_candidate_branches": len(operation_branches),
        "anchor_candidate_documents": len(anchor_doc_ids),
        "candidate_branches": len(routed_branches),
        "candidate_documents": len(anchor_doc_ids),
        "selected_documents": [{
            "doc_id": row["doc_id"], "doc": row["doc"],
            "source_kind": row["source_kind"], "scope_kind": row["scope_kind"],
            "enforce": row["enforce"], "revised": row["revised"],
        } for row in documents],
        "anchor_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
        } for row in anchor_branches],
        "operation_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
        } for row in operation_branches],
        "routed_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
        } for row in routed_branches],
        "document_scoped_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
        } for row in document_scoped],
        "scoped_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
        } for row in scoped],
        "seed_pool_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
        } for row in seed_pool],
        "document_scoped_branches": len(document_scoped),
        "scoped_candidate_branches": len(scoped),
        "seed_pool_branches": len(seed_pool), "seed_mode": seed_mode,
        "structure": structure_meta,
        "intersection": _intersection(routed_branches, all_terms),
        "scoped_intersection": _intersection(scoped, all_terms),
        "seeds": [{"doc_id": row.doc_id, "node": row.node, "doc": row.doc,
                   "path": row.path, "terms": list(row.terms),
                   "origin": row.origin, "mandatory": row.mandatory,
                   "mandatory_reason": row.mandatory_reason} for row in seeds],
        "expansion": expansion_meta,
        "review_candidates": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
            "relation_reason": row.relation_reason,
            "mandatory": row.mandatory,
            "mandatory_reason": row.mandatory_reason,
        } for row in review_candidates],
        "mandatory_candidates": len(mandatory),
        "selection_calls": len(audit), "selection": audit,
        "selected": [{
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "terms": list(row.terms), "origin": row.origin,
            "relation_reason": row.relation_reason,
            "mandatory": row.mandatory,
            "mandatory_reason": row.mandatory_reason,
        } for row in selected],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    return sections, meta
