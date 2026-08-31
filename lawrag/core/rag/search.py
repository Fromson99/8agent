"""검색 사다리 — 정확 일치 → 부분 일치 → 본문+벡터 하이브리드.

원본(DELTAFlow RAG)의 라이브 검색을 그대로 옮겼고, 마지막 단만 하이브리드로
넓혔다 (결정 변경 2026-08-10 — lawrag/core/rag/vector.py 머리 참조):

    ① 정확(MAIN)   색인값이 질의 **안에** 통째로 들어 있다 (value ⊂ query).
                    사용자가 그 말을 정확히 가리킨 것이므로, 하나라도 있으면
                    아래 단은 돌지 않는다.
    ② 부분(PARTIAL) 질의 토큰이 색인값 안에 있거나, 질의↔색인값의 trigram
                    유사도가 문턱(0.5)을 넘는다. 정확 일치가 없을 때만.
    ③ 본문+벡터    제목·용어가 다 빗나가면 블록 렉시컬(tf·idf + 접두 확장)과
                    구역 벡터(사전 임베딩 + 질의 코사인)를 **RRF 로 융합**한다.
                    벡터 색인·모델이 없으면 렉시컬만 — 오프라인에서도 돈다.

용어 기반이라는 정체성은 그대로다: 벡터는 ①②가 빗나간 뒤에만 돌고, 벡터가
찾아준 착지는 승격 후보로 적재되어(rag 라우터) 용어가 되기를 기다린다 —
벡터 히트는 종착이 아니라 용어의 씨앗이다.

방향이 보통 검색과 반대(①)인 이유: 색인값은 짧고(제목·용어) 질의는 길다.
"부당권유행위 금지가 뭐야?" 안에 색인값 "부당권유행위 금지" 가 들어 있다.

매 단은 기록을 남긴다(ladder). 어느 단에서 무엇이 잡혔는지 없으면 답변의
근거 경위를 사람이 되짚을 수 없다.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from lawrag.core.rag.index import Index, norm
from lawrag.core.rag.controls import value as control_value

log = logging.getLogger("lawrag.core.rag.search")

# 원본의 실측 튜닝값을 그대로 둔다 — REVERSE_MATCH_TRIGRAM_THRESHOLD 0.5 는
# 흔한 긴 토큰이 수백 건씩 잡히는 폭주와 정상 매칭 보존 사이의 균형점이었다.
TRIGRAM_THRESHOLD = float(control_value("search.trigram_min"))
MIN_TOKEN_LEN = 2
MAIN_LIMIT = int(control_value("search.main_hits_max"))
PARTIAL_LIMIT = int(control_value("search.partial_hits_max"))
BLOCK_LIMIT = int(control_value("search.block_hits_max"))

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


@dataclass
class Hit:
    target: str                  # 병합 단위 — "doc:{id}:{node}" | "term:{key}" | "block:{id}:{idx}"
    kind: str                    # "제목" | "용어" | "본문"
    value: str                   # 매칭된 표면형
    score: float
    match: str                   # "정확" | "부분" | "본문"
    reasons: list = field(default_factory=list)
    doc_id: str = ""
    doc: str = ""
    node: Optional[int] = None
    block: Optional[int] = None
    occurrences: list = field(default_factory=list)


@dataclass
class SearchResult:
    query: str
    mode: str                    # "정확" | "부분" | "본문" | "없음"
    hits: list
    ladder: list                 # [{"stage","count","note"}] — 회수 경위


# ------------------------------------------------------------------ trigram
def _trigrams(s: str) -> set:
    """pg_trgm 방식 — 앞에 둘, 뒤에 하나 패딩. norm 된 문자열에 쓴다."""
    if not s:
        return set()
    s = "  " + s + " "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def similarity(a: str, b: str) -> float:
    """trigram 집합의 겹침/합집합 — Postgres `similarity()` 와 같은 정의."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ------------------------------------------------------------------ 토큰
def tokens_of(query: str) -> list[str]:
    """부분 일치용 토큰. 한글 연속은 통째로 하나다 — 조사를 떼지 않는다.
    떼는 일은 색인 쪽 접두 확장이 한다."""
    out = []
    for t in _TOKEN_RE.findall(query or ""):
        if len(t) >= MIN_TOKEN_LEN:
            out.append(t)
    return out


def _ascii_only(s: str) -> bool:
    return bool(s) and all(ord(c) < 128 for c in s)


def _token_in_query(value: str, query_lower: str) -> bool:
    """ASCII 값의 오탐 방지 — 'ER'⊂'filtER' 를 막는다. 경계 기준은 ASCII
    영숫자다: 한글 조사가 붙은 'RFQ에' 는 경계로 인정해 통과시킨다."""
    v = (value or "").strip().casefold()
    if not v:
        return False
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])",
                     query_lower) is not None


# ------------------------------------------------------------------ 사다리
def _done(res: SearchResult, t0: float) -> SearchResult:
    """반환 직전 관측 한 줄 — 어느 단이 몇 건을 잡았는지가 회수 경위의 뼈대다."""
    log.info("검색 '%s' → %s %d건 (%.0fms) — %s",
             res.query[:60], res.mode, len(res.hits),
             (time.perf_counter() - t0) * 1000,
             " / ".join(f"{l['stage']} {l['count']}" for l in res.ladder) or "사다리 없음")
    return res


def search(index: Index, query: str) -> SearchResult:
    t0 = time.perf_counter()
    q = (query or "").strip()
    qn = norm(q)
    q_lower = q.casefold()
    ladder: list[dict] = []
    if not qn:
        return _done(SearchResult(query=q, mode="없음", hits=[], ladder=ladder), t0)

    # ── ① 정확 — 색인값 ⊂ 질의. 긴 값 우선(더 구체적인 지목이 이긴다). ──
    main: dict[str, Hit] = {}
    for e in index.entries:
        if len(e.key) < 2 or e.key not in qn:
            continue
        # ASCII 값은 원문에서 낱말 경계를 요구한다 — 공백 제거 매칭은 한글의
        # 붙여쓰기 흔들림을 살리자는 것이지 영문 부분 문자열을 열자는 게 아니다.
        if _ascii_only(e.key) and not _token_in_query(e.value, q_lower):
            continue
        score = min(1.0, 0.5 + (len(e.key) / max(len(qn), 1)) * 0.5)
        cur = main.get(e.target)
        if cur is None or score > cur.score:
            main[e.target] = Hit(
                target=e.target, kind=e.kind, value=e.value, score=round(score, 4),
                match="정확", reasons=[f"질의에 '{e.value}' 포함"],
                doc_id=e.doc_id, doc=e.doc, node=e.node,
                occurrences=e.occurrences)
    if main:
        hits = sorted(main.values(), key=lambda h: (-len(norm(h.value)), -h.score))
        hits = hits[:MAIN_LIMIT]
        ladder.append({"stage": "정확 일치", "count": len(hits),
                       "note": "색인값이 질의 안에 통째로 있음 — 부분 일치는 돌지 않음"})
        return _done(SearchResult(query=q, mode="정확", hits=hits, ladder=ladder), t0)
    ladder.append({"stage": "정확 일치", "count": 0, "note": "없음"})

    # ── ② 부분 — 토큰 ⊂ 색인값, 그리고 질의↔값 trigram. ──
    toks = tokens_of(q)
    partial: dict[str, Hit] = {}
    for e in index.entries:
        if len(e.key) < 2:
            continue
        hit_toks = [t for t in toks if norm(t) in e.key]
        sub_score = (min(0.6, sum(len(norm(t)) for t in hit_toks) / max(len(e.key), 1))
                     if hit_toks else 0.0)
        sim = similarity(qn, e.key)
        score, reasons = 0.0, []
        if hit_toks:
            score = sub_score
            reasons.append("토큰 " + "·".join(hit_toks))
        if sim >= TRIGRAM_THRESHOLD:
            if reasons:
                # 두 방식이 겹치면 어느 한쪽보다 늘 앞선다 — 원본의 의도적 설계.
                score = min(1.0, score + sim * 0.4)
                reasons.append(f"trigram {sim:.2f}")
            else:
                score = sim * 0.6
                reasons = [f"trigram {sim:.2f}"]
        if score <= 0.0:
            continue
        cur = partial.get(e.target)
        if cur is None or score > cur.score:
            partial[e.target] = Hit(
                target=e.target, kind=e.kind, value=e.value, score=round(score, 4),
                match="부분", reasons=reasons,
                doc_id=e.doc_id, doc=e.doc, node=e.node,
                occurrences=e.occurrences)
    if partial:
        hits = sorted(partial.values(), key=lambda h: -h.score)[:PARTIAL_LIMIT]
        ladder.append({"stage": "부분 일치", "count": len(hits),
                       "note": f"토큰·trigram(≥{TRIGRAM_THRESHOLD})"})
        return _done(SearchResult(query=q, mode="부분", hits=hits, ladder=ladder), t0)
    ladder.append({"stage": "부분 일치", "count": 0, "note": "없음"})

    # ── ③ 본문+벡터 하이브리드 — 렉시컬 블록과 벡터 구역을 RRF 로 융합. ──
    scores: dict[tuple, float] = {}
    matched: dict[tuple, list[str]] = {}
    for kw in toks:
        for k in index.expand(kw):
            post = index.postings().get(k)
            if not post:
                continue
            idf = index.idf(k)
            w = 1.0 if k == kw.casefold() else 0.6      # 접두 확장은 감점
            for key, tf in post.items():
                scores[key] = scores.get(key, 0.0) + tf * idf * w
                if k not in matched.setdefault(key, []):
                    matched[key].append(k)
    lex_blocks = sorted(scores.items(), key=lambda kv: -kv[1])[:BLOCK_LIMIT]

    from lawrag.core.rag import vector as vector_mod          # 지연 — 없으면 빈 목록
    try:
        vec_nodes = vector_mod.search(q, doc_ids=index.scope)   # [(doc_id, node, cos)] — 스코프 안만
    except Exception as exc:
        log.warning("벡터 단 실패 — 렉시컬만으로 간다: %s", exc)
        vec_nodes = []
    # 전역 vector cache가 다른 Index 인스턴스(테스트·스코프 교체 전 corpus)의
    # 좌표를 들고 있을 수 있다. _fuse는 원래 이를 버리지만 n_vec는 버리기 전
    # 길이를 세어 빈 결과를 '벡터/하이브리드'로 잘못 표시했다. 현재 index에서
    # 실제로 열 수 있는 좌표만 채널 적중으로 센다.
    vec_nodes = [row for row in vec_nodes
                 if row[0] in index.docs
                 and row[1] in index.docs[row[0]].by_id]

    hits = _fuse(index, lex_blocks, matched, vec_nodes)
    n_lex, n_vec = len(lex_blocks), len(vec_nodes)
    note = (f"렉시컬 {n_lex} + 벡터 {n_vec} → RRF 융합" if n_lex and n_vec
            else "블록 렉시컬 — tf·idf, 접두 확장" if n_lex
            else f"벡터만 — 코사인 상위 {n_vec}" if n_vec else "없음")
    ladder.append({"stage": "본문+벡터", "count": len(hits), "note": note})
    mode = ("하이브리드" if n_lex and n_vec
            else "본문" if n_lex else "벡터" if n_vec else "없음")
    return _done(SearchResult(query=q, mode=mode, hits=hits, ladder=ladder), t0)


def _fuse(index: Index, lex_blocks: list, matched: dict,
          vec_nodes: list) -> list:
    """RRF(k=60) — 점수 스케일이 다른 두 랭킹을 순위로만 합친다.

    융합 단위는 **구역(doc, node)** 이다: 렉시컬은 블록을 잡지만 답변 조립은
    구역으로 가므로, 같은 구역의 블록 여럿은 최고 순위 하나로 접는다.
    벡터로만 잡힌 구역은 kind="벡터" 로 표시된다 — 이 표시가 rag 라우터의
    승격 후보 적재(벡터 히트 = 용어의 씨앗)와 튜플 기록의 근거다.
    """
    K = 60
    fused: dict[tuple, float] = {}
    lex_best: dict[tuple, tuple] = {}      # (doc,node) -> (block, rank, score)
    for rank, ((doc_id, blk), s) in enumerate(lex_blocks):
        v = index.docs.get(doc_id)
        if v is None:
            continue
        node = (v.owner(blk) or {}).get("id")
        key = (doc_id, node)
        fused[key] = fused.get(key, 0.0) + 1.0 / (K + rank + 1)
        if key not in lex_best:
            lex_best[key] = (blk, rank, s)
    vec_score: dict[tuple, float] = {}
    for rank, (doc_id, node, cos) in enumerate(vec_nodes):
        if index.docs.get(doc_id) is None:
            continue
        key = (doc_id, node)
        fused[key] = fused.get(key, 0.0) + 1.0 / (K + rank + 1)
        vec_score[key] = cos

    hits = []
    for key, f in sorted(fused.items(), key=lambda kv: -kv[1])[:BLOCK_LIMIT]:
        doc_id, node = key
        v = index.docs[doc_id]
        lex = lex_best.get(key)
        reasons = []
        if lex is not None:
            blk_idx = lex[0]
            reasons.append("키워드 " + "·".join(matched.get((doc_id, blk_idx), [])))
        if key in vec_score:
            reasons.append(f"벡터 코사인 {vec_score[key]:.2f}")
        if lex is not None:
            blk = v.block_by_idx.get(lex[0]) or {}
            hits.append(Hit(
                target=f"block:{doc_id}:{lex[0]}", kind="본문",
                value=(blk.get("text") or "")[:80], score=round(f, 4),
                match="하이브리드" if key in vec_score else "본문",
                reasons=reasons, doc_id=doc_id, doc=v.name,
                node=node, block=lex[0]))
        else:
            hits.append(Hit(
                target=f"doc:{doc_id}:{node}", kind="벡터",
                value=v.path(node) or v.name, score=round(f, 4),
                match="벡터", reasons=reasons,
                doc_id=doc_id, doc=v.name, node=node))
    return hits
