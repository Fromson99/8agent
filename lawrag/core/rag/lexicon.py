"""용어집 — 코퍼스가 실제로 쓰는 낱말의 한 색인, 그리고 질문을 그 낱말로 옮기는 자리.

회수 전략(2026-08-18 사용자 결정)의 1단계다:

    사용자 질문
      1-a  정확한 keyword 매칭      질문 낱말이 용어집에 통째로 있나 (결정론)
      1-b  vector → 용어집          없으면 낱말을 임베딩해 **용어 목록**에 쏜다 —
                                    조문 본문(6만 마디)이 아니라 용어(2만)라 짧고
                                    문체 격차가 작다
      1-c  LLM 판별 + 조립          1-b 가 데려온 후보를 보고 필요한 것만 남기고,
                                    "누가→누구에게→무엇을→한다" 프레임으로 조립
      → 프레임 색인(frames.py) 필드 일치 조회 (framematch)
      → 용어를 하나도 못 잡으면 루프(법 스코프 깔때기)

용어집의 재료 (전부 코퍼스에서 나온 표면형 — 지어낸 낱말 없음):
    프레임 어휘   actor · act · target · object  (frames/, 하이쿠 추출)
    정의어        "X"란 · 이하별칭                (definitions.py, 결정론)
    법령명·약칭   문서명 · aliases.json
항목마다 (표면형, 종류, 출처 좌표들). 고유 표면형 21,336(2026-08-18 전수).

임베딩은 표면형마다 한 번, data/lexicon/terms.npz 에 캐시(names+emb — 어휘가 바뀌면
없는 낱말만 인코딩하는 낱말 단위 증분). CPU 에서 시간 단위라 매 질의마다 다시 재면 안 된다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

def _np():
    """numpy 지연 로드 — 무거운 의존은 모듈 수준 금지(tests/architecture).
    np 를 쓰는 메서드가 첫 줄에서 `np = _np()` 로 받는다 — 전역 주입이 아니라
    지역 바인딩이라, 테스트가 __new__ 로 __init__ 을 우회해도 성립한다."""
    import numpy
    return numpy

from lawrag.core.rag import definitions as definitions_mod
from lawrag.core.rag import frames as frames_mod
from lawrag.core.rag.index import Index, store_path

log = logging.getLogger("lawrag.core.rag.lexicon")

FIELDS = ("actor", "act", "target", "object")
TERM_MIN, TERM_MAX = 2, 40
NEIGHBORS = 8              # 1-b 가 슬롯마다 보여주는 이웃 수 — 메뉴는 작아야 고를 만하다
NEIGHBOR_MIN = 0.60        # 이웃 문턱 — 이 아래는 무관


def _pack(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def lexicon_dir() -> Path:
    return Path(os.environ.get("RAG_LEXICON_DIR", store_path().parent / "lexicon"))


class Lexicon:
    """용어 표면형 → {kinds, coords}. 필드별 임베딩 행렬(캐시)."""

    def __init__(self, index: Index, cache: bool = True,
                 doc_ids: Optional[set] = None):
        """doc_ids 를 주면 그 문서들의 용어만 — 파일럿·실측용(전수 임베딩은 CPU 에서
        시간 단위라, 골든 사례가 있는 문서만 먼저 재고 넓힌다)."""
        np = _np()
        self.index = index
        self.doc_ids = set(doc_ids) if doc_ids else None
        self.terms: dict[str, dict] = {}       # 표면형 → {"kinds": set, "coords": set[(doc,node)], "fields": set}
        self._collect()
        self.names = list(self.terms)
        self.packed = [_pack(t) for t in self.names]
        self._by_field: dict[str, np.ndarray] = {}   # 필드 → 그 필드에 나오는 항목 idx
        for f in FIELDS + ("정의어",):
            self._by_field[f] = np.array([i for i, t in enumerate(self.names)
                                          if f in self.terms[t]["fields"]], dtype=np.int64)
        self.vec: Optional[np.ndarray] = None
        if cache:
            self._embed()

    # ------------------------------------------------------------ 모으기
    def _add(self, term: str, kind: str, field: str, doc_id: str, node) -> None:
        t = re.sub(r"\s+", " ", term or "").strip()
        if not (TERM_MIN <= len(t) <= TERM_MAX):
            return
        e = self.terms.setdefault(t, {"kinds": set(), "fields": set(), "coords": set()})
        e["kinds"].add(kind)
        e["fields"].add(field)
        if doc_id and node is not None:
            e["coords"].add((doc_id, node))

    def _collect(self) -> None:
        for did, v in self.index.docs.items():      # 어휘는 코퍼스 전체 — 스코프는 좌표(narrow)에서 건다(임베딩 캐시 하나)
            if self.doc_ids is not None and did not in self.doc_ids:
                continue
            for r in frames_mod.load(did):
                for f in FIELDS:
                    self._add(r.get(f) or "", "프레임", f, did, r.get("node"))
            for d in definitions_mod.defs(v):
                self._add(d["term"], "정의어", "정의어", did, d["node"])
            self._add(v.name, "법령명", "법령명", did, None)
        p = store_path().parent / "aliases.json"
        if p.is_file():
            try:
                for a, full in json.loads(p.read_text("utf-8")).items():
                    self._add(a, "약칭", "법령명", "", None)
            except Exception:
                pass

    # ------------------------------------------------------------ 임베딩
    def _embed(self) -> None:
        """표면형마다 한 번 — **낱말 단위 증분**. 캐시(terms.npz)는 names+emb 를 함께
        들고, 어휘가 바뀌면(문서 추가·프레임 재생성) 없는 낱말만 인코딩하고 합집합을
        다시 쓴다. 옛 형식(terms-N.npz: emb+sig 만)은 sig 가 맞을 때만 통째로 쓴다.
        2026-08-19 실측 — 57→140 문서 재편 한 번에 4만 낱말 1h43m 을 다시 내던 것이
        새 낱말 몫만 남는다."""
        np = _np()
        from lawrag.core import embedding
        if not embedding.available() or not self.names:
            return
        d = lexicon_dir()
        d.mkdir(parents=True, exist_ok=True)
        known: dict[str, np.ndarray] = {}
        for f in sorted(d.glob("terms*.npz")):
            try:
                z = np.load(f, allow_pickle=False)
                if "names" in z.files:
                    for n, v in zip(z["names"].tolist(), z["emb"]):
                        known.setdefault(n, v)
                elif f.name == f"terms-{len(self.names)}.npz":       # 옛 형식 — sig 일치 때만
                    sig = hashlib.sha1("\n".join(self.names).encode("utf-8")).hexdigest()[:16]
                    if str(z["sig"]) == sig:
                        for n, v in zip(self.names, z["emb"]):
                            known.setdefault(n, v)
            except Exception:
                continue
        missing = [n for n in self.names if n not in known]
        if missing:
            log.info("용어집 임베딩 — 전체 %d · 캐시 재사용 %d · 새로 %d",
                     len(self.names), len(self.names) - len(missing), len(missing))
            emb = np.asarray(embedding.encode(missing), dtype=np.float32)
            emb /= (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
            for n, v in zip(missing, emb):
                known[n] = v
            names = list(known)                                   # 합집합 — 파일럿·전수가 서로 안 지운다
            np.savez_compressed(d / "terms.npz", names=np.array(names, dtype=str),
                                emb=np.stack([known[n] for n in names]).astype(np.float16))
        self.vec = np.stack([np.asarray(known[n], dtype=np.float32) for n in self.names])

    # ------------------------------------------------------------ 1-a 정확
    def exact(self, question: str, cap: int = 12) -> list[dict]:
        """질문 안에 통째로 있는 용어 — 긴 것 우선. [{term, kinds, fields, coords}]"""
        pq = _pack(question)
        hits = [(t, p) for t, p in zip(self.names, self.packed)
                if len(p) >= 2 and p in pq]
        hits.sort(key=lambda x: -len(x[1]))
        out, covered = [], []
        for t, p in hits:
            if any(p in c for c in covered):        # "개인정보처리자"가 잡히면 "개인정보"는 그 안
                continue
            covered.append(p)
            e = self.terms[t]
            out.append({"term": t, "kinds": sorted(e["kinds"]), "fields": sorted(e["fields"]),
                        "coords": sorted(e["coords"])[:8]})
            if len(out) >= cap:
                break
        return out

    # ------------------------------------------------------------ 1-b 벡터 → 용어집
    def neighbors(self, word: str, field: Optional[str] = None,
                  k: int = NEIGHBORS, min_cos: float = NEIGHBOR_MIN) -> list[dict]:
        """낱말 → 용어집 이웃 (필드 안에서). [{term, cos, coords}]"""
        np = _np()
        if self.vec is None or not word:
            return []
        from lawrag.core import embedding
        q = np.asarray(embedding.encode_one(word), dtype=np.float32)
        q /= (np.linalg.norm(q) + 1e-9)
        idxs = self._by_field.get(field) if field else None
        if idxs is None or len(idxs) == 0:
            idxs = np.arange(len(self.names))
        sims = self.vec[idxs] @ q
        order = np.argsort(-sims)[:k]
        out = []
        for j in order:
            if sims[j] < min_cos:
                break
            t = self.names[int(idxs[j])]
            out.append({"term": t, "cos": round(float(sims[j]), 3),
                        "coords": sorted(self.terms[t]["coords"])[:8]})
        return out


_cache: dict = {}


def current(index: Index, doc_ids: Optional[set] = None) -> Lexicon:
    """색인 객체별로 한 번 — Index 가 새로 지어지면 용어집도 새로.
    RAG_LEXICON_DOCS(문서명 부분일치, 쉼표 구분)가 있으면 그 문서들만 — 파일럿."""
    if doc_ids is None:
        env = os.environ.get("RAG_LEXICON_DOCS", "")
        if env:
            keys = [k.strip() for k in env.split(",") if k.strip()]
            doc_ids = {d for d, v in index.docs.items() if any(k in v.name for k in keys)}
    # 스코프 사본은 docs 를 공유한다 — 용어집은 코퍼스 전체 어휘라 스코프와 무관하게
    # 하나면 된다(임베딩이 비싸다). 키는 docs 객체로 — 색인이 다시 서면 새 dict 다.
    key = (id(index.docs), tuple(sorted(doc_ids)) if doc_ids else None)
    lx = _cache.get(key)
    if lx is None:
        lx = Lexicon(index, doc_ids=doc_ids)
        _cache.clear()
        _cache[key] = lx
    return lx
