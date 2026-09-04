"""Tier 2 통계 깔때기 — 후보 생성·지표·군집·게이트의 계약을 시험한다.

Kiwi 는 무겁지만 로컬 결정론이라 그대로 시험한다(미설치 환경은 skip).
임베딩 모델은 시험에서 부르지 않는다 — cluster 는 벡터를 받는 순수 함수다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.index import DocView                          # noqa: E402
from lawrag.core.terms import gate as gate_mod                     # noqa: E402
from lawrag.core.terms import hierarchy as hier_mod                # noqa: E402
from lawrag.core.terms import relations as rel_mod                 # noqa: E402
from lawrag.core.terms.cluster import cluster                      # noqa: E402
from lawrag.core.terms.stats import Scored, _contiguous_in, _g2_pair, score  # noqa: E402

kiwi_ok = True
try:                                                        # pragma: no cover
    import kiwipiepy  # noqa: F401
except Exception:                                           # pragma: no cover
    kiwi_ok = False

needs_kiwi = pytest.mark.skipif(not kiwi_ok, reason="kiwipiepy 미설치")


def _view(texts, doc_id="d1", name="A.pdf"):
    nodes = [{"id": 1, "parent": None, "level": 1, "surface": "제1조",
              "title": "총칙", "page": 1, "span": [0, len(texts)], "block": None}]
    blocks = [{"idx": i, "page": 1, "text": t, "kind": "text"}
              for i, t in enumerate(texts)]
    return DocView.build(doc_id, {"name": name}, {"nodes": nodes, "blocks": blocks})


@needs_kiwi
def test_후보와_공기_한_스캔(monkeypatch):
    from lawrag.core.terms.candidates import harvest

    h = harvest([_view(["신탁재산은 신탁보수를 공제한다.",
                        "신탁재산의 운용방법은 수익자가 정한다."])])
    assert "신탁재산" in h.mentions and len(h.mentions["신탁재산"]) == 2
    # 최대 후보끼리의 공기 쌍이 남는다 (부분열끼리는 아니다). a·b 는 사전순.
    pairs = {(c.a, c.b) for c in h.cooccurs}
    assert tuple(sorted(("신탁재산", "신탁보수"))) in pairs


@needs_kiwi
def test_나열은_공기가_아니라_형제다():
    from lawrag.core.terms.candidates import harvest

    h = harvest([_view(["펌프, 압축기 및 송풍기 등의 회전기기를 점검한다."])])
    kinds = {(c.a, c.b): c.kind for c in h.cooccurs}
    assert kinds.get(("송풍기", "압축기")) == "enum" or \
        kinds.get(("압축기", "펌프")) == "enum"


def test_g2_는_붙어다니는_쌍에_높다():
    # (a,b)가 늘 함께: k11=10, a 10회, b 10회, 전체 1000 → 매우 유의
    strong = _g2_pair(10, 10, 10, 1000)
    weak = _g2_pair(10, 100, 100, 1000)     # 관측 = 기대(10) — 우연 수준
    assert strong > 10.83 > weak


def test_proto_rel_은_회피_쌍을_승격하지_않는다():
    """G² 는 양측 검정 — 기대보다 훨씬 **적게** 공기해도 유의가 나온다.
    그런 쌍(음의 연관)은 관계 후보가 아니다."""
    from lawrag.core.terms.candidates import Cooccur, HarvestResult

    h = HarvestResult()
    h.n_sents = 1000
    # a·b 각각 500문장에 나오는데 함께는 5번뿐 — 기대 250 대비 극단적 회피
    for i in range(5):
        h.cooccurs.append(Cooccur(a="가나", b="다라", pattern="", kind="cooccur",
                                  doc_id=f"d{i % 2}", block=i, sent=i))
    for i in range(1000):
        terms = set()
        if i < 500:
            terms.add("가나")
        if i >= 495:
            terms.add("다라")
        if terms:
            h.sent_terms[("dx", 0, i)] = terms
    rows = rel_mod.aggregate(h, {"가나", "다라"})
    assert rows[0]["status"] == "proto"          # 유의하지만 승격은 안 된다


def test_cvalue_중첩_보정():
    """"안전밸브"가 늘 "압력안전밸브" 안에서만 나오면 감점된다."""
    from lawrag.core.terms.candidates import HarvestResult, Mention

    h = HarvestResult()

    def put(key, toks, n):
        for i in range(n):
            h.mentions.setdefault(key, []).append(Mention(
                surface=key, key=key, tokens=toks, doc_id="d1", doc="A",
                node=1, block=i, page=1, sent=0, in_heading=False))

    put("압력안전밸브", ("압력", "안전", "밸브"), 10)
    put("안전밸브", ("안전", "밸브"), 10)          # 전부 중첩 출현이라 가정
    rows = {r.key: r for r in score(h, min_tf=1)}
    # 중첩 보정: f(안전밸브)=10 에서 포함자 빈도 10 을 뺀다 → C-value 0
    assert rows["안전밸브"].cvalue == 0.0
    assert rows["압력안전밸브"].cvalue > 0


def test_토큰_포함은_연속_부분열만():
    assert _contiguous_in(("안전", "밸브"), ("압력", "안전", "밸브"))
    assert not _contiguous_in(("압력", "밸브"), ("압력", "안전", "밸브"))


def test_greedy_군집은_임계로_가른다():
    import numpy as np

    v = np.array([[1, 0], [0.99, 0.14], [0, 1]], dtype=np.float32)
    v = v / np.linalg.norm(v, axis=1, keepdims=True)
    groups = cluster(v, [0, 1, 2], threshold=0.95)
    assert sorted(map(sorted, groups)) == [[0, 1], [2]]


def test_계층_어휘포함은_접미_일치만():
    toks = {"압력안전밸브": ("압력", "안전", "밸브"),
            "안전밸브": ("안전", "밸브"), "압력계": ("압력", "계")}
    rows = [Scored(key=k, surface=k, n_tokens=len(t), tf=3, df=1, heading=0)
            for k, t in toks.items()]
    edges = hier_mod.lexical(rows, toks)
    pairs = {(e["child"], e["parent"]) for e in edges}
    assert ("압력안전밸브", "안전밸브") in pairs
    assert ("압력계", "압력안전밸브") not in pairs        # 머리 명사가 다르다
    assert not any(c == "압력계" for c, _ in pairs)


def test_proto_rel_승격_임계():
    from lawrag.core.terms.candidates import Cooccur, HarvestResult

    h = HarvestResult()
    h.n_sents = 100
    for i in range(6):                                     # 6회 공기, 2문서
        h.cooccurs.append(Cooccur(a="밸브", b="배관", pattern="에 설치",
                                  kind="cooccur", doc_id=f"d{i % 2}",
                                  block=i, sent=0))
        h.sent_terms[(f"d{i % 2}", i, 0)] = {"밸브", "배관"}
    rows = rel_mod.aggregate(h, {"밸브", "배관"})
    assert rows[0]["status"] == "candidate"
    assert rows[0]["top_patterns"][0]["pattern"] == "에 설치"


def test_게이트_변별력과_유령용어(tmp_path):
    """어디에나 있는 어휘는 기각되고, LLM 이 지어낸 대표명은 무시된다."""
    from lawrag.core.terms.candidates import HarvestResult, Mention
    from lawrag.core.terms.judge import Verdict

    h = HarvestResult()
    h.n_blocks = 20

    def put(key, blocks):
        for b in blocks:
            h.mentions.setdefault(key, []).append(Mention(
                surface=key, key=key, tokens=(key,), doc_id="d1", doc="A",
                node=1, block=b, page=1, sent=0, in_heading=False, text="문맥"))

    put("규정", list(range(18)))         # 블록 90% — 변별력 없음
    put("신탁보수", [0, 1])              # 블록 10% — 통과
    rows = [Scored(key="규정", surface="규정", n_tokens=1, tf=9, df=1, heading=0),
            Scored(key="신탁보수", surface="신탁보수", n_tokens=1, tf=2, df=1, heading=0)]
    verdicts = {1: Verdict(cluster=1, is_term=True, canonical="수탁보수료",  # 유령
                           confidence=0.9, type="개념")}
    rep = gate_mod.register(h, rows, [["규정"], ["신탁보수"]], verdicts,
                            tmp_path / "g.json")
    assert any("변별력" in r["이유"] for r in rep["rejected"])
    assert rep["added"] == ["신탁보수"]      # 유령 대표명이 아니라 실제 표면형


def test_군집은_병합하지_않는다(tmp_path):
    """결정 (2026-08-10): 추출은 표면형별 개별 등재 — 군집은 판정 배치
    단위일 뿐, 케노니컬 병합은 검수·질의 루프가 벌어서 만든다."""
    import json

    from lawrag.core.terms.candidates import HarvestResult, Mention
    from lawrag.core.terms.judge import Verdict

    h = HarvestResult()
    h.n_blocks = 40
    for key, blocks in (("안전밸브", [0, 1]), ("압력안전밸브", [2])):
        for b in blocks:
            h.mentions.setdefault(key, []).append(Mention(
                surface=key, key=key, tokens=(key,), doc_id="d1", doc="A",
                node=1, block=b, page=1, sent=0, in_heading=False, text="문맥"))
    rows = [Scored(key="안전밸브", surface="안전밸브", n_tokens=1, tf=2, df=1, heading=0),
            Scored(key="압력안전밸브", surface="압력안전밸브", n_tokens=1, tf=1, df=1, heading=0)]
    # 한 군집으로 묶여 왔고 판정도 별칭 병합을 제안하지만 —
    verdicts = {0: Verdict(cluster=0, is_term=True, canonical="안전밸브",
                           aliases=["압력안전밸브"], confidence=0.95, type="개념")}
    rep = gate_mod.register(h, rows, [["안전밸브", "압력안전밸브"]], verdicts,
                            tmp_path / "g.json")
    data = {t["key"]: t for t in
            json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))["terms"]}
    assert sorted(rep["added"]) == ["안전밸브", "압력안전밸브"]   # 둘 다 개별 용어
    assert data["안전밸브"]["surfaces"] == ["안전밸브"]           # 별칭 흡수 없음
    assert data["압력안전밸브"]["surfaces"] == ["압력안전밸브"]