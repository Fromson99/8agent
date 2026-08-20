"""GenOS 임베딩 백엔드(lawrag/core/embedding.py) — OpenAI 호환 /v1/embeddings 앞에서
encode() 계약(정규화 float32 행렬, 실패 시 None + available() False)이 서는지.
가짜 서빙 하나를 스레드로 띄운다. embed_sections 가 그 위에서 색인을 만들고
vector.search 가 같은 백엔드로 질의를 임베딩해 그 색인을 치는 것까지 본다.
"""
from __future__ import annotations

import importlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("requests", reason="requests 필요")
np = pytest.importorskip("numpy", reason="numpy 필요")

DIM = 8


def _vec(text: str) -> list[float]:
    """결정적 가짜 임베딩 — 글자 코드로 만든 8차원. 같은 글은 같은 벡터,
    비슷한 글은 비슷한 벡터(앞 글자들이 지배)."""
    v = [0.0] * DIM
    for i, ch in enumerate(text[:64]):
        v[i % DIM] += (ord(ch) % 97) / 97.0
    return v


def _fresh():
    """lawrag.core.embedding 을 진짜로 다시 적재한다 — sys.modules 만 지우면
    `from core import embedding` 이 패키지 속성의 옛 모듈을 돌려준다."""
    import lawrag.core as core
    sys.modules.pop("lawrag.core.embedding", None)
    if hasattr(core, "embedding"):
        delattr(core, "embedding")
    return importlib.import_module("lawrag.core.embedding")


class _Fake:
    def __init__(self, reject: bool = False):
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                if self.path.endswith("/v1/models"):
                    b = json.dumps({"data": [{"id": "fake-embed"}]}).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self.end_headers(); self.wfile.write(b)
                else:
                    self.send_response(404); self.end_headers()

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                req["_auth"] = self.headers.get("Authorization", "")
                outer.requests.append(req)
                if reject:
                    self.send_response(400); self.end_headers(); return
                inp = req["input"] if isinstance(req["input"], list) else [req["input"]]
                body = {"object": "list", "model": req.get("model"),
                        "data": [{"object": "embedding", "index": i, "embedding": _vec(t)}
                                 for i, t in reversed(list(enumerate(inp)))]}   # 역순 — index 로 정렬하는지
                b = json.dumps(body).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.end_headers(); self.wfile.write(b)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


@pytest.fixture(autouse=True)
def _restore_reloaded_modules():
    """_fresh()·재적재가 갈아끼운 모듈을 테스트마다 되돌린다.

    다른 파일의 fixture 는 **자기 import 시점의 모듈 객체**에 패치를 건다
    (test_lexicon 의 fake_embed 가 embedding.encode 를 monkeypatch). 여기서
    sys.modules 를 뽑고 재적재한 새 객체가 남으면 그 패치는 낡은 객체에 걸려
    허공에 뜬다 — 실측(2026-08-20): 전체 스위트에서 lexicon 3건·switches 2건이
    이 파일 뒤에서만 실패했다. 스냅샷을 되돌릴 때 부모 패키지 속성도 같이
    되돌린다 — `from lawrag.core import embedding` 은 속성을 먼저 본다."""
    import lawrag.core  # noqa: F401 — 스냅샷 대상 적재 보장
    targets = lambda: [m for m in list(sys.modules)  # noqa: E731
                       if m == "lawrag.core.embedding"
                       or m.startswith(("lawrag.core.rag", "lawrag.core.terms"))]
    saved = {m: sys.modules[m] for m in targets()}
    yield
    for m in targets():
        del sys.modules[m]
    sys.modules.update(saved)
    for m, mod in saved.items():
        parent, _, child = m.rpartition(".")
        if parent in sys.modules:
            setattr(sys.modules[parent], child, mod)


@pytest.fixture()
def emb(monkeypatch):
    def _set(url):
        for k in ("EMBED_BACKEND", "GENOS_EMBED_MODEL", "GENOS_EMBED_KEY", "RAG_VECTOR"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("GENOS_EMBED_URL", url)
        monkeypatch.setenv("GENOS_LLM_KEY", "shared-key")      # EMBED_KEY 없으면 LLM 키를 쓴다
        monkeypatch.setenv("GENOS_EMBED_BATCH", "2")
        return _fresh()
    return _set


def test_backend_selection(monkeypatch):
    embedding = _fresh()
    monkeypatch.delenv("EMBED_BACKEND", raising=False)
    monkeypatch.delenv("GENOS_EMBED_URL", raising=False)
    assert embedding.backend() == "local"
    monkeypatch.setenv("GENOS_EMBED_URL", "http://x")
    assert embedding.backend() == "genos" and embedding.available()
    monkeypatch.setenv("RAG_VECTOR", "0")
    assert not embedding.available()                    # 명시적으로 끄면 둘 다 아니다
    monkeypatch.delenv("RAG_VECTOR")
    monkeypatch.setenv("EMBED_BACKEND", "local")
    assert embedding.backend() == "local"


def test_encode_batches_sorts_normalizes(emb):
    fake = _Fake()
    try:
        embedding = emb(fake.url)
        texts = ["제19조 설명의무", "제20조 부당권유 금지", "신탁재산 구분"]
        m = embedding.encode(texts)
        assert m is not None and m.shape == (3, DIM) and m.dtype == np.float32
        assert np.allclose(np.linalg.norm(m, axis=1), 1.0)         # 정규화
        # 배치 2 → 요청 2번, 모델은 /v1/models 에서, 키는 LLM 키 공용
        assert len(fake.requests) == 2 and fake.requests[0]["model"] == "fake-embed"
        assert fake.requests[0]["_auth"] == "Bearer shared-key"
        assert fake.requests[0]["input"] == texts[:2] and fake.requests[1]["input"] == texts[2:]
        # 서버가 역순으로 줘도 index 로 되돌린다
        want = np.asarray([_vec(t) for t in texts], dtype=np.float32)
        want /= np.linalg.norm(want, axis=1, keepdims=True)
        assert np.allclose(m, want, atol=1e-6)
        assert np.allclose(embedding.encode_one(texts[0]), want[0], atol=1e-6)
    finally:
        fake.close()


def test_failure_is_remembered(emb):
    fake = _Fake(reject=True)
    try:
        embedding = emb(fake.url)
        assert embedding.available()
        assert embedding.encode(["x"]) is None
        assert not embedding.available()                # 이후 질의마다 다시 실패하지 않는다
    finally:
        fake.close()


def test_index_build_and_query_same_backend(emb, tmp_path, monkeypatch):
    """그쪽에서 벡터를 다시 만드는 길 — embed_sections 가 genos 로 색인을 굽고,
    vector.search 가 같은 genos 로 질의를 임베딩해 그 색인에서 찾는다."""
    fake = _Fake()
    try:
        emb(fake.url)
        store = tmp_path / "structure"; store.mkdir()
        d = store / "abc123"; d.mkdir()
        (d / "meta.json").write_text(json.dumps({"doc_id": "abc123", "name": "시험 규정"}), encoding="utf-8")
        (d / "result.json").write_text(json.dumps({
            "doc": "시험 규정",
            "nodes": [{"id": 0, "parent": None, "level": 0, "family": "kr_article",
                       "surface": "제1조", "title": "제1조 설명의무", "ordinal": [1],
                       "page": 1, "block": 0, "span": [0, 1], "n_children": 0},
                      {"id": 1, "parent": None, "level": 0, "family": "kr_article",
                       "surface": "제2조", "title": "제2조 부당권유 금지", "ordinal": [2],
                       "page": 1, "block": 1, "span": [1, 2], "n_children": 0}],
            "blocks": [{"idx": 0, "page": 1, "text": "제1조 설명의무 — 금융투자업자는 설명하여야 한다", "node": 0},
                       {"idx": 1, "page": 1, "text": "제2조 부당권유 금지 — 하여서는 아니 된다", "node": 1}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("STRUCTURE_STORE", str(store))
        monkeypatch.setenv("RAG_VECTOR_STORE", str(tmp_path / "embeddings" / "sections"))
        for m in [m for m in list(sys.modules) if m.startswith(("lawrag.core.rag", "lawrag.core.terms"))]:
            del sys.modules[m]
        from lawrag.core.terms import embed_sections
        rep = embed_sections.run(store, tmp_path / "embeddings" / "sections")
        assert rep["sections"] == 2 and rep["fresh"] == 2
        from lawrag.core.rag import vector
        hits = vector.search("설명의무", topk=2)
        assert hits and hits[0][0] == "abc123"
        # 색인 굽기(배치 2 → 1요청) + 질의 1요청, 전부 같은 서빙으로
        assert len(fake.requests) == 2
    finally:
        fake.close()
