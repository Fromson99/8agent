"""T23. 청크 검색 — facet 필터 + 렉시컬 + refs 확장 (SPEC §D2-3~5).

벡터 인덱스가 없다. 매 단계가 설명 가능하다:
    topic/role 필터 → 키워드 점수 → refs 1-hop 확장 → small-to-big 서빙
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

import comparators as cmp
from ontology import Ontology
from schema import Chunk, ChunkDocument


@dataclass
class Hit:
    chunk: Chunk
    score: float
    why: list[str] = dc_field(default_factory=list)


def _terms(text: str) -> list[str]:
    out, buf = [], ""
    for ch in text:
        if ch.isalnum() or "가" <= ch <= "힣":
            buf += ch
        else:
            if len(buf) > 1:
                out.append(buf.casefold())
            buf = ""
    if len(buf) > 1:
        out.append(buf.casefold())
    return out


class ChunkIndex:
    """렉시컬 인덱스. BM25 대신 문서 빈도 가중 점수 — 의존성 없이 설명 가능하게."""

    def __init__(self, doc: ChunkDocument):
        self.doc = doc
        self.postings: dict[str, dict[str, int]] = {}
        for c in doc.chunks:
            for t in _terms(c.text):
                self.postings.setdefault(t, {}).setdefault(c.chunk_id, 0)
                self.postings[t][c.chunk_id] += 1
        self.n = max(len(doc.chunks), 1)
        self.by_id = {c.chunk_id: c for c in doc.chunks}

    def expand(self, keyword: str) -> list[str]:
        """조사가 붙은 어절을 어휘와 잇는다 — 형태소 분석기 없이.

        `중도해지는` ↔ 색인어 `중도해지`, `보수` ↔ `신탁보수`.
        한쪽이 다른 쪽의 접두이면 같은 말로 본다. 완전일치가 있으면 그것만 쓴다.
        """
        k = keyword.casefold()
        if k in self.postings:
            return [k]
        out = [t for t in self.postings
               if len(t) >= 2 and (t.startswith(k) or k.startswith(t))]
        out.sort(key=lambda t: (abs(len(t) - len(k)), t))
        return out[:4]

    def search(self, keywords: list[str], candidates: Optional[set[str]] = None,
               top: int = 5) -> list[Hit]:
        import math
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        for kw in keywords:
            for k in self.expand(kw):
                post = self.postings.get(k)
                if not post:
                    continue
                idf = math.log(1 + self.n / len(post))
                # 부분일치는 감점 — 완전일치가 먼저 오게 한다
                w = 1.0 if k == kw.casefold() else 0.6
                for cid, tf in post.items():
                    if candidates is not None and cid not in candidates:
                        continue
                    scores[cid] = scores.get(cid, 0.0) + tf * idf * w
                    if k not in matched.setdefault(cid, []):
                        matched[cid].append(k)
        hits = [Hit(self.by_id[cid], round(s, 3), [f"키워드 {'·'.join(matched[cid])}"])
                for cid, s in scores.items()]
        hits.sort(key=lambda h: -h.score)
        return hits[:top]


def facet_filter(doc: ChunkDocument, topic: Optional[str] = None,
                 role: Optional[str] = None) -> set[str]:
    out = set()
    for c in doc.chunks:
        if topic and c.topic != topic:
            continue
        if role and c.role != role:
            continue
        out.add(c.chunk_id)
    return out


def expand_refs(doc: ChunkDocument, hits: list[Hit], onto: Ontology,
                hops: int = 1) -> list[Chunk]:
    """§D2-5 — 선택된 청크의 refs 를 따라 참조 조·별지를 컨텍스트에 합류.

    `제3조` 는 그 조의 청크를, `별지1` 은 **인용한 조에 연결된 별지 필드만** 끌어온다.
    별지 전체를 붙이면 21건씩 딸려와 컨텍스트가 망가진다 — 링크는 조 단위로 좁힌다.
    """
    appendix_role = {f"별지{p.appendix_no}": p.role
                     for p in onto.appendix_parts() if p.appendix_no}
    seen = {h.chunk.chunk_id for h in hits}
    extra: list[Chunk] = []
    frontier = list(hits)
    for _ in range(hops):
        nxt = []
        for h in frontier:
            src = h.chunk
            for r in src.refs:
                role = appendix_role.get(r)
                for c in doc.chunks:
                    if c.chunk_id in seen:
                        continue
                    if role is not None:
                        # 별지 참조 — 인용한 조에 걸린 필드만 (cross_ref 로 이미 연결돼 있다)
                        ok = c.role == role and src.article and c.article == src.article
                    else:
                        ok = c.article == r and c.role == onto.default_role()
                    if ok:
                        seen.add(c.chunk_id)
                        extra.append(c)
                        nxt.append(Hit(c, 0.0, [f"refs←{r}"]))
        frontier = nxt
    return extra


def serve_small_to_big(doc: ChunkDocument, chunk: Chunk) -> list[Chunk]:
    """§D2-5 — 항 단위로 매칭됐어도 컨텍스트에는 부모 조 전체를 담는다."""
    if not chunk.article:
        return [chunk]
    return [c for c in doc.chunks
            if c.article == chunk.article and c.role == chunk.role]
