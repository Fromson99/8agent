"""Tier 2 점수화 — 참조 코퍼스 불필요 지표 4종 + Borda (ontology_kg §4.9).

    C-value            중첩 보정 unithood — "안전 밸브"가 항상 "압력 안전 밸브"
                       안에서만 나오면 감점 (Frantzi & Ananiadou)
    G² (unithood)      다단어 구성 토큰의 공기 우도비 — 저빈도 강건 (Dunning)
    Domain Consensus   문서 분포 엔트로피 — 합의 용어인가 한 문서의 사투리인가
    구조 가중           heading 출현 보너스 (TermExtractor 방식 — L1 구조의 이점)

결합은 **Borda 랭킹 앙상블** — 개별 점수 가중치를 튜닝하지 않는다. 지표마다
순위를 매기고 순위 합으로 자른다 (문헌상 가장 값싼 개선, Zhang 2008).

LL keyness·Log Ratio(참조 코퍼스 대비)는 위키 덤프 확보 후의 백로그다 —
지금 지표는 전부 도메인 코퍼스 안에서 계산된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.terms.candidates import HarvestResult


@dataclass
class Scored:
    key: str
    surface: str                  # 최빈 표면형 — 클러스터·판정의 대표
    n_tokens: int
    tf: int
    df: int                       # 문서 수
    heading: int                  # 제목 출현 수
    cvalue: float = 0.0
    g2: float = 0.0               # 단일어는 0 (해당 없음 — Borda 에서 중간 순위)
    dc: float = 0.0               # Domain Consensus 0~1
    borda: int = 0
    rank: int = 0


def _g2_pair(k11: int, k1_: int, k_1: int, n: int) -> float:
    """2×2 공기표의 G² 우도비. 0 보호를 위해 0*ln0=0 규약."""
    def term(obs: float, exp: float) -> float:
        return obs * math.log(obs / exp) if obs > 0 and exp > 0 else 0.0

    k12, k21 = k1_ - k11, k_1 - k11
    k22 = n - k1_ - k_1 + k11
    if min(k11, k12, k21, k22) < 0 or n <= 0:
        return 0.0
    e11 = k1_ * k_1 / n
    e12 = k1_ * (n - k_1) / n
    e21 = (n - k1_) * k_1 / n
    e22 = (n - k1_) * (n - k_1) / n
    return 2 * (term(k11, e11) + term(k12, e12) + term(k21, e21) + term(k22, e22))


def _contiguous_in(a: tuple, b: tuple) -> bool:
    """a 가 b 의 연속 부분열인가 — 문자열 포함이 아니라 **토큰** 포함이다.
    ("수익" ⊂ "수익자의부담" 같은 형태소 경계를 가로지르는 우연 포함 방지)"""
    if len(a) >= len(b):
        return False
    for i in range(len(b) - len(a) + 1):
        if b[i:i + len(a)] == a:
            return True
    return False


def score(h: HarvestResult, min_tf: int = 2) -> list[Scored]:
    """후보 전부에 지표를 매기고 Borda 순위를 붙여 정렬해 돌려준다."""
    rows: list[Scored] = []
    toks_of: dict[str, tuple] = {}
    for key, ms in h.mentions.items():
        tf = len(ms)
        if tf < min_tf:
            continue
        surfaces: dict[str, int] = {}
        docs: dict[str, int] = {}
        heading = 0
        for m in ms:
            surfaces[m.surface] = surfaces.get(m.surface, 0) + 1
            docs[m.doc_id] = docs.get(m.doc_id, 0) + 1
            heading += m.in_heading
        toks = max((m.tokens for m in ms), key=len)
        toks_of[key] = toks
        # Domain Consensus — 정규화 엔트로피. 문서가 하나뿐이면 0 (사투리).
        dc = 0.0
        if len(docs) > 1:
            dc = -sum((c / tf) * math.log2(c / tf) for c in docs.values())
            dc /= math.log2(len(docs))
        rows.append(Scored(
            key=key, surface=max(surfaces, key=surfaces.get),
            n_tokens=len(toks), tf=tf, df=len(docs), heading=heading, dc=dc))

    by_key = {r.key: r for r in rows}

    # C-value — 후보끼리의 토큰 중첩. 후보 수백~수천 규모라 이중 루프로 충분;
    # 규모가 커지면 접미 색인으로 바꾼다 (지금 최적화하지 않는다).
    contained: dict[str, list[str]] = {r.key: [] for r in rows}
    for a in rows:
        ta = toks_of[a.key]
        for b in rows:
            if a.key != b.key and _contiguous_in(ta, toks_of[b.key]):
                contained[a.key].append(b.key)
    for r in rows:
        length = math.log2(r.n_tokens + 1)
        nest = contained[r.key]
        if not nest:
            r.cvalue = length * r.tf
        else:
            r.cvalue = length * (r.tf - sum(by_key[k].tf for k in nest) / len(nest))

    # G² unithood — 다단어 후보의 인접 토큰 쌍 중 **가장 약한 고리**.
    n = max(h.n_tokens, 1)
    for r in rows:
        toks = toks_of[r.key]
        if len(toks) < 2:
            continue
        g2s = []
        for i in range(len(toks) - 1):
            pair = (toks[i], toks[i + 1])
            g2s.append(_g2_pair(h.bigram.get(pair, 0),
                                h.unigram.get(pair[0], 0),
                                h.unigram.get(pair[1], 0), n))
        r.g2 = min(g2s) if g2s else 0.0

    _borda(rows)
    rows.sort(key=lambda r: r.rank)
    return rows


def _borda(rows: list[Scored]) -> None:
    """지표별 순위 투표. 단일어는 G² 순위에서 중간값을 받는다 —
    지표가 적용 불가인 것과 나쁜 것은 다르다."""
    if not rows:
        return
    n = len(rows)

    def ranks(keyfn, applicable=None) -> dict[str, int]:
        app = [r for r in rows if applicable is None or applicable(r)]
        app.sort(key=keyfn, reverse=True)
        out = {r.key: i for i, r in enumerate(app)}
        mid = len(app) // 2
        return {r.key: out.get(r.key, mid) for r in rows}

    parts = [
        ranks(lambda r: r.cvalue),
        ranks(lambda r: r.g2, applicable=lambda r: r.n_tokens >= 2),
        ranks(lambda r: r.dc),
        ranks(lambda r: (r.heading, r.tf)),
        ranks(lambda r: r.tf),
    ]
    for r in rows:
        r.borda = sum(p[r.key] for p in parts)
    for i, r in enumerate(sorted(rows, key=lambda r: r.borda)):
        r.rank = i + 1
