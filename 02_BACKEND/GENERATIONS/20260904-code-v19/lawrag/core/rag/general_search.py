"""질문에서 뽑은 일반 검색어로 문서 본문을 찾는 독립 회수 채널.

기존 용어 검색은 ``색인값 ⊂ 질문``인 역방향 매칭이다. 정확하지만, 문서를
찾기 전에 사람이 표면형과 좌표를 용어집에 올려야 한다. 이 모듈은 그 정본을
건드리지 않고 보통 검색의 방향을 하나 더 연다.

    질문 --(LLM)--> 검색어 2~8개 --(결정론)--> 제목·본문 BM25 --> 문서/구역

LLM은 검색어만 만든다. 문서와 좌표는 반드시 현재 ``Index``에서 결정론으로
되짚으며, LLM이 코퍼스에 없는 말을 만들면 그 말은 ``unmatched``로 남고 0건이
된다. 검색어 추출이 실패하거나 LLM이 없을 때는 질문의 어절을 쓰는 작은 폴백이
있어 검색 기능 자체는 죽지 않는다.

이 모듈은 기존 ``search.py``나 용어집 인덱스를 변경하지 않는다. 따라서 일반
검색의 성능을 별도로 검수한 뒤 합류 순서와 예산만 호출부에서 정할 수 있다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from lawrag.core.rag.index import Index


KEYWORDS_MAX = 8
HITS_MAX = 8
HITS_PER_DOCUMENT = 2
EXPANSIONS_PER_TOKEN = 12
KEYWORD_CHARS_MAX = 60

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
_SPACE_RE = re.compile(r"\s+")
_TRIM_RE = re.compile(r"^[\s\"'`‘’“”「」『』,.;:!?()〔〕\[\]{}]+|"
                      r"[\s\"'`‘’“”「」『』,.;:!?()〔〕\[\]{}]+$")

# LLM이 없을 때만 쓰는 최소 폴백이다. 검색 품질을 이 목록으로 해결하려는 것이
# 아니라 질문 꼬리만 검색어가 되는 명백한 오염을 피하려는 안전장치다.
_FALLBACK_STOP = frozenset({
    "알려줘", "알려주세요", "알려", "설명해줘", "설명해주세요",
    "뭐야", "무엇인가요", "무엇인지", "어떻게", "어떤", "관련", "규정",
    "조항", "문서", "검색", "찾아줘", "찾아주세요", "있나요", "있어",
})

KEYWORD_SYSTEM = (
    "너는 문서 검색어 작성기다. 사용자 질문에 답할 근거 문서를 찾기 위한 "
    "검색어를 만든다. 검색은 제목과 본문의 글자를 대조한다.\n"
    "규칙: ① 2~8개의 짧은 낱말 또는 짧은 구로 쓴다. ② 질문의 핵심 주체·대상·"
    "행위·조건을 보존한다. ③ '알려줘'·'어떻게'·'규정' 같은 검색 가치 없는 말은 "
    "뺀다. ④ 문서에 쓰였을 법한 표현을 우선하되, 질문에 근거 없는 법령명·"
    "기관명·수치를 지어내지 마라. ⑤ 조사나 어미를 떼어 본문에 붙어도 찾기 쉽게 "
    "쓴다(예: '성과보수를 지급'→'성과보수', '지급'). ⑥ 동의어는 널리 쓰이는 것만 "
    "별도 검색어로 추가한다."
)
KEYWORD_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["keywords"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class KeywordPlan:
    question: str
    keywords: tuple[str, ...]
    via: str                       # "llm" | "fallback" | "llm-empty"

    def as_dict(self) -> dict:
        return {"question": self.question, "keywords": list(self.keywords),
                "via": self.via}


@dataclass(frozen=True)
class KeywordHit:
    doc_id: str
    doc: str
    node: Optional[int]
    path: str
    block: Optional[int]
    page: Optional[int]
    score: float
    matched: tuple[str, ...]
    excerpt: str = ""

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id, "doc": self.doc, "node": self.node,
            "path": self.path, "block": self.block, "page": self.page,
            "score": self.score, "matched": list(self.matched),
            "excerpt": self.excerpt,
        }


@dataclass
class GeneralSearchResult:
    question: str
    keywords: list[str]
    hits: list[KeywordHit] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    extractor: str = ""

    @property
    def documents(self) -> list[dict]:
        """구역 히트를 관련 문서 목록으로 접는다. 문서 점수는 최고 구역을
        중심으로 하고, 같은 문서의 추가 근거는 작게 보탠다."""
        grouped: dict[str, dict] = {}
        for hit in self.hits:
            row = grouped.setdefault(hit.doc_id, {
                "doc_id": hit.doc_id, "doc": hit.doc, "score": 0.0,
                "matched": [], "sections": [],
            })
            if not row["sections"]:
                row["score"] = hit.score
            else:
                row["score"] += hit.score * 0.20
            for keyword in hit.matched:
                if keyword not in row["matched"]:
                    row["matched"].append(keyword)
            row["sections"].append({
                "node": hit.node, "path": hit.path, "block": hit.block,
                "page": hit.page, "score": hit.score,
                "excerpt": hit.excerpt,
            })
        rows = list(grouped.values())
        for row in rows:
            row["score"] = round(row["score"], 4)
        rows.sort(key=lambda row: (-row["score"], row["doc"]))
        return rows

    def as_dict(self) -> dict:
        return {
            "question": self.question, "keywords": self.keywords,
            "extractor": self.extractor, "unmatched": self.unmatched,
            "documents": self.documents,
            "hits": [hit.as_dict() for hit in self.hits],
        }

    def as_search_result(self):
        """기존 answer.assemble에 넣을 수 있는 SearchResult 어댑터."""
        from lawrag.core.rag.search import Hit, SearchResult

        hits = [Hit(
            target=f"block:{hit.doc_id}:{hit.block}", kind="일반검색",
            value=" · ".join(hit.matched), score=hit.score, match="검색어",
            reasons=[f"본문·제목 검색어: {' · '.join(hit.matched)}"],
            doc_id=hit.doc_id, doc=hit.doc, node=hit.node, block=hit.block,
        ) for hit in self.hits]
        note = (f"{self.extractor} 추출: {' · '.join(self.keywords)}"
                if self.keywords else f"{self.extractor}: 검색어 없음")
        if self.unmatched:
            note += " · 미일치 " + " · ".join(self.unmatched)
        return SearchResult(
            query=self.question,
            mode="일반검색" if hits else "없음",
            hits=hits,
            ladder=[{"stage": "LLM 검색어+일반검색", "count": len(hits),
                     "note": note}],
        )


def _clean_keyword(value: object) -> str:
    text = _SPACE_RE.sub(" ", str(value or "")).strip()
    text = _TRIM_RE.sub("", text).strip()
    if len(text) > KEYWORD_CHARS_MAX:
        text = text[:KEYWORD_CHARS_MAX].rstrip()
    if len("".join(_TOKEN_RE.findall(text))) < 2:
        return ""
    return text


def _dedupe(values: Iterable[object], cap: int = KEYWORDS_MAX) -> list[str]:
    out, seen = [], set()
    for raw in values:
        value = _clean_keyword(raw)
        key = _SPACE_RE.sub("", value).casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= cap:
            break
    return out


def _fallback_keywords(question: str) -> list[str]:
    values = []
    for token in _TOKEN_RE.findall(question or ""):
        value = token.strip()
        if len(value) < 2 or value.casefold() in _FALLBACK_STOP:
            continue
        values.append(value)
    return _dedupe(values)


def fallback_keywords(question: str) -> list[str]:
    """LLM 없이 질문 원문의 검색 가능 어절만 반환하는 공개 API."""
    return _fallback_keywords(question)


def extract_keywords(llm, question: str) -> KeywordPlan:
    """질문을 검색어로 바꾼다. LLM 실패는 질문 어절 폴백으로 내려간다."""
    q = (question or "").strip()
    if not q:
        return KeywordPlan(q, (), "fallback")
    if llm is None:
        return KeywordPlan(q, tuple(_fallback_keywords(q)), "fallback")
    out = llm.structured(
        "rag.general_search.keywords", KEYWORD_SYSTEM, f"[질문]\n{q}",
        KEYWORD_SCHEMA, max_tokens=400, effort="low",
    )
    if out is None:
        return KeywordPlan(q, tuple(_fallback_keywords(q)), "fallback")
    keywords = _dedupe(out.get("keywords") or [])
    return KeywordPlan(q, tuple(keywords), "llm" if keywords else "llm-empty")


@dataclass
class _Corpus:
    postings: dict[str, dict[tuple[str, int], int]]
    lengths: dict[tuple[str, int], int]
    average_length: float
    block_count: int


def _corpus(index: Index) -> _Corpus:
    """스코프별 Index 인스턴스에 일반검색용 통계를 지연 캐시한다."""
    cached = getattr(index, "_general_search_corpus", None)
    if cached is not None:
        return cached
    postings = index.postings()
    lengths: dict[tuple[str, int], int] = {}
    for rows in postings.values():
        for key, tf in rows.items():
            lengths[key] = lengths.get(key, 0) + tf
    # 텍스트가 전부 한 글자 토큰이어도 N에는 포함한다.
    block_count = sum(len(view.blocks) for view in index.entry_docs.values()) or 1
    average = sum(lengths.values()) / max(len(lengths), 1)
    cached = _Corpus(postings, lengths, max(average, 1.0), block_count)
    setattr(index, "_general_search_corpus", cached)
    return cached


def _query_tokens(keyword: str) -> list[str]:
    return _dedupe(_TOKEN_RE.findall(keyword), cap=KEYWORDS_MAX)


def _expansions(corpus: _Corpus, query_token: str) -> list[tuple[str, float]]:
    """질문 검색어와 본문 어절을 접두 관계로 잇는다.

    ``성과보수``로 ``성과보수를``을 찾는 한국어 조사 흔들림과, ``RFQ``
    대소문자를 같은 규칙으로 다룬다. 너무 짧은 ASCII 부분 문자열은
    확장하지 않아 ``ER`` ⊂ ``filter`` 오탐을 막는다.
    """
    q = query_token.casefold()
    if not q:
        return []
    rows = []
    if q in corpus.postings:
        rows.append((q, 1.0))
    allow_prefix = not (q.isascii() and len(q) < 3)
    if allow_prefix:
        for term in corpus.postings:
            if term == q or len(term) < 2:
                continue
            if term.startswith(q) or q.startswith(term):
                ratio = min(len(q), len(term)) / max(len(q), len(term))
                rows.append((term, 0.65 + 0.25 * ratio))
    rows.sort(key=lambda row: (-row[1], abs(len(row[0]) - len(q)), row[0]))
    return rows[:EXPANSIONS_PER_TOKEN]


def _bm25(tf: int, doc_len: int, average: float, idf: float) -> float:
    k1, b = 1.2, 0.75
    denom = tf + k1 * (1.0 - b + b * doc_len / average)
    return idf * (tf * (k1 + 1.0)) / max(denom, 1e-9)


def _packed(value: str) -> str:
    return _SPACE_RE.sub("", value or "").casefold()


def _field_match(field: str, token: str) -> bool:
    q = token.casefold()
    for value in _TOKEN_RE.findall(field or ""):
        value = value.casefold()
        if value == q:
            return True
        if not (q.isascii() and len(q) < 3) and (
                value.startswith(q) or q.startswith(value)):
            return True
    return False


def search_keywords(index: Index, keywords: Iterable[str], *, question: str = "",
                    limit: int = HITS_MAX,
                    per_document: int = HITS_PER_DOCUMENT,
                    extractor: str = "provided") -> GeneralSearchResult:
    """검색어를 본문·제목에 OR 검색하고, 다중 검색어 적중을 순위에 보탠다.

    한 검색어라도 맞으면 후보가 된다(일반 검색의 recall). 여러 독립 검색어가
    같은 구역에 모일수록 coverage 보너스로 위에 선다(precision). 같은 문서의
    한 긴 구역이 결과를 독식하지 않도록 문서당 구역 수도 제한한다.
    """
    clean = _dedupe(keywords)
    result = GeneralSearchResult(question=question, keywords=clean,
                                 extractor=extractor)
    if not clean or limit <= 0:
        return result

    corpus = _corpus(index)
    scores: dict[tuple[str, int], float] = {}
    matched: dict[tuple[str, int], set[str]] = {}
    keyword_seen: dict[str, bool] = {keyword: False for keyword in clean}

    for keyword in clean:
        # 한 keyword 안의 여러 토큰은 각각 가장 좋은 표면 확장 하나만 기여한다.
        for query_token in _query_tokens(keyword):
            best: dict[tuple[str, int], float] = {}
            for term, expansion_weight in _expansions(corpus, query_token):
                rows = corpus.postings.get(term) or {}
                df = len(rows)
                idf = math.log(1.0 + (corpus.block_count - df + 0.5) / (df + 0.5))
                for key, tf in rows.items():
                    score = _bm25(tf, corpus.lengths.get(key, 1),
                                  corpus.average_length, idf) * expansion_weight
                    if score > best.get(key, 0.0):
                        best[key] = score
            for key, score in best.items():
                scores[key] = scores.get(key, 0.0) + score
                matched.setdefault(key, set()).add(keyword)
                keyword_seen[keyword] = True

        # 제목·문서명은 본문과 별도 필드다. 일치하면 해당 구역 좌표를 바로 연다.
        qtokens = _query_tokens(keyword)
        for doc_id, view in index.entry_docs.items():
            doc_match = any(_field_match(view.name, token) for token in qtokens)
            for node in view.nodes:
                label = view.path(node.get("id"))
                title_match = any(_field_match(label, token) for token in qtokens)
                if not (doc_match or title_match):
                    continue
                span = node.get("span") or [0, 0]
                block = node.get("block")
                if block is None:
                    block = span[0]
                key = (doc_id, block)
                scores[key] = scores.get(key, 0.0) + (1.8 if title_match else 1.1)
                matched.setdefault(key, set()).add(keyword)
                keyword_seen[keyword] = True

    # 여러 검색어가 한 블록에 모이면 합의 신호다. 온전한 구가 실제 본문에 있으면
    # 작은 phrase 보너스도 준다. 점수의 절대값은 외부 채널과 섞지 않는다.
    for key in list(scores):
        coverage = len(matched.get(key) or ())
        scores[key] *= 1.0 + 0.18 * max(0, coverage - 1)
        doc_id, block = key
        view = index.docs.get(doc_id)
        text = ((view.block_by_idx.get(block) or {}).get("text") or "") if view else ""
        packed_text = _packed(text)
        for keyword in matched.get(key) or ():
            phrase = _packed(keyword)
            if len(phrase) >= 4 and phrase in packed_text:
                scores[key] += 0.75

    # 블록을 답변 단위인 구역으로 접는다. 같은 구역의 여러 블록은 최고 점수를
    # 중심으로 2·3번째 근거를 조금만 보탠다.
    section_rows: dict[tuple[str, Optional[int]], dict] = {}
    for (doc_id, block), score in sorted(scores.items(), key=lambda row: -row[1]):
        view = index.docs.get(doc_id)
        if view is None:
            continue
        owner = view.owner(block)
        node = (owner or {}).get("id")
        skey = (doc_id, node)
        block_row = view.block_by_idx.get(block) or {}
        row = section_rows.get(skey)
        if row is None:
            row = {"score": score, "best_block": block,
                   "matched": set(matched.get((doc_id, block)) or ()),
                   "excerpt": re.sub(r"\s+", " ", block_row.get("text") or "")[:240]}
            section_rows[skey] = row
        else:
            row["score"] += score * 0.20
            row["matched"].update(matched.get((doc_id, block)) or ())

    ranked = sorted(section_rows.items(), key=lambda row: (-row[1]["score"], row[0]))
    per_doc_count: dict[str, int] = {}
    for (doc_id, node), row in ranked:
        if per_doc_count.get(doc_id, 0) >= per_document:
            continue
        view = index.docs[doc_id]
        block = row["best_block"]
        block_row = view.block_by_idx.get(block) or {}
        hit_keywords = tuple(k for k in clean if k in row["matched"])
        result.hits.append(KeywordHit(
            doc_id=doc_id, doc=view.name, node=node,
            path=view.path(node) or view.name, block=block,
            page=block_row.get("page") or (view.by_id.get(node) or {}).get("page"),
            score=round(row["score"], 4), matched=hit_keywords,
            excerpt=row["excerpt"],
        ))
        per_doc_count[doc_id] = per_doc_count.get(doc_id, 0) + 1
        if len(result.hits) >= limit:
            break

    result.unmatched = [keyword for keyword in clean if not keyword_seen[keyword]]
    return result


def search_question(index: Index, question: str, llm=None, *,
                    limit: int = HITS_MAX) -> GeneralSearchResult:
    """질문 → 검색어 추출 → 일반 검색의 한 번짜리 공개 진입점."""
    plan = extract_keywords(llm, question)
    return search_keywords(index, plan.keywords, question=plan.question,
                           limit=limit, extractor=plan.via)


def fuse_with_registered(index: Index, registered, general: GeneralSearchResult,
                         *, limit: int = HITS_MAX) -> list[dict]:
    """기존 역매칭 사다리와 일반검색을 구역 좌표 기준 RRF로 합친다.

    기존 점수(부분 문자열·trigram·벡터 RRF)와 일반검색 BM25는 척도가 달라
    숫자를 직접 더하면 안 된다. 각 채널의 순위만 합치고, 두 채널에 함께 잡힌
    구역은 자연스럽게 위로 올린다. 용어 히트는 저장된 출현 좌표로 펼친다.
    """
    rrf_k = 60
    rows: dict[tuple[str, Optional[int]], dict] = {}

    def push(doc_id: str, node, *, channel: str, rank: int, matched: str,
             block=None, page=None, excerpt: str = "") -> None:
        view = index.docs.get(doc_id)
        if view is None or not index.in_scope(doc_id):
            return
        key = (doc_id, node)
        row = rows.setdefault(key, {
            "doc_id": doc_id, "doc": view.name, "node": node,
            "path": view.path(node) or view.name, "block": block,
            "page": page or (view.by_id.get(node) or {}).get("page"),
            "score": 0.0, "channels": [], "matched": [], "excerpt": excerpt,
        })
        row["score"] += 1.0 / (rrf_k + rank + 1)
        if channel not in row["channels"]:
            row["channels"].append(channel)
        if matched and matched not in row["matched"]:
            row["matched"].append(matched)
        if row.get("block") is None and block is not None:
            row["block"] = block
        if row.get("page") is None and page is not None:
            row["page"] = page
        if not row.get("excerpt") and excerpt:
            row["excerpt"] = excerpt

    registered_rank = 0
    registered_seen: set[tuple[str, Optional[int]]] = set()
    for hit in registered.hits:
        coords = []
        if hit.kind == "용어":
            coords = sorted(
                hit.occurrences or [],
                key=lambda row: 0 if row.get("via") in ("제목", "정의") else 1,
            )
        elif hit.doc_id:
            coords = [{"doc_id": hit.doc_id, "node": hit.node,
                       "block": hit.block}]
        for coord in coords:
            key = (coord.get("doc_id", ""), coord.get("node"))
            if not key[0] or key in registered_seen:
                continue
            registered_seen.add(key)
            push(key[0], key[1], channel="역매칭", rank=registered_rank,
                 matched=hit.value, block=coord.get("block"), page=coord.get("page"))
            registered_rank += 1

    for rank, hit in enumerate(general.hits):
        push(hit.doc_id, hit.node, channel="일반검색", rank=rank,
             matched=" · ".join(hit.matched), block=hit.block, page=hit.page,
             excerpt=hit.excerpt)

    out = sorted(rows.values(), key=lambda row: (-row["score"], row["doc"],
                                                  row["node"] is None,
                                                  row["node"] or -1))[:limit]
    for row in out:
        row["score"] = round(row["score"], 6)
    return out
