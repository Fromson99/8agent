"""용어집 임베딩 캐시 — 낱말 단위 증분 (2026-08-19 재편 실측에서)."""
import numpy as np
import pytest

from lawrag.core import embedding
from lawrag.core.rag import lexicon as lexicon_mod


def _lex(names):
    lx = lexicon_mod.Lexicon.__new__(lexicon_mod.Lexicon)
    lx.names = list(names)
    lx.vec = None
    return lx


@pytest.fixture
def fake_embed(monkeypatch, tmp_path):
    calls = []

    def encode(texts):
        calls.append(list(texts))
        # 낱말마다 결정적 벡터 — 길이로 구분
        return np.array([[len(t), 1.0, 0.0] for t in texts], dtype=np.float32)

    monkeypatch.setattr(embedding, "available", lambda: True)
    monkeypatch.setattr(embedding, "encode", encode)
    monkeypatch.setenv("RAG_LEXICON_DIR", str(tmp_path))
    return calls


def test_first_build_encodes_all_and_writes_named_cache(fake_embed, tmp_path):
    lx = _lex(["세무공무원", "국세청장"])
    lx._embed()
    assert lx.vec.shape == (2, 3)
    assert fake_embed == [["세무공무원", "국세청장"]]
    z = np.load(tmp_path / "terms.npz", allow_pickle=False)
    assert set(z["names"].tolist()) == {"세무공무원", "국세청장"}


def test_vocabulary_growth_encodes_only_new_words(fake_embed, tmp_path):
    _lex(["세무공무원", "국세청장"])._embed()
    lx = _lex(["국세청장", "개인정보처리자", "세무공무원"])       # 순서 바뀌고 하나 늘었다
    lx._embed()
    assert fake_embed[-1] == ["개인정보처리자"]                  # 새 낱말만
    assert lx.vec.shape == (3, 3)
    # 행 순서는 self.names 순서 — 캐시 순서가 아니라
    assert lx.vec[0][0] == pytest.approx(len("국세청장") / np.sqrt(len("국세청장") ** 2 + 1), abs=1e-3)
    z = np.load(tmp_path / "terms.npz", allow_pickle=False)
    assert len(z["names"]) == 3                                   # 합집합


def test_pilot_subset_does_not_erase_full_cache(fake_embed, tmp_path):
    _lex(["가나다", "라마바", "사아자"])._embed()
    _lex(["가나다"])._embed()                                     # 파일럿(부분) — 인코딩 0
    assert len(fake_embed) == 1
    z = np.load(tmp_path / "terms.npz", allow_pickle=False)
    assert len(z["names"]) == 3


def test_legacy_cache_reused_when_sig_matches(fake_embed, tmp_path):
    import hashlib
    names = ["하나", "둘"]
    sig = hashlib.sha1("\n".join(names).encode("utf-8")).hexdigest()[:16]
    np.savez_compressed(tmp_path / "terms-2.npz", emb=np.ones((2, 3), dtype=np.float32), sig=np.array(sig))
    lx = _lex(names)
    lx._embed()
    assert fake_embed == []                                       # 옛 형식 통째로 재사용
    assert lx.vec.shape == (2, 3)
