from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")


class Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._body


class Session:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self.exists = False

    def get(self, url, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        self.calls.append(("get", url, None))
        return Response(200 if self.exists else 404,
                        {"result": {"status": "green", "points_count": 2}})

    def put(self, url, json=None, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        self.calls.append(("put", url, json))
        self.exists = True
        return Response()

    def delete(self, url, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        self.calls.append(("delete", url, None))
        self.exists = False
        return Response()

    def post(self, url, json=None, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        self.calls.append(("post", url, json))
        return Response(body={"result": [{"score": 0.91,
                                           "payload": {"doc_id": "d1", "node": 3}}]})


def test_sync_and_search(monkeypatch, tmp_path: Path):
    from lawrag.core.rag import qdrant_store

    session = Session()
    monkeypatch.setattr(qdrant_store, "_session", lambda: session)
    monkeypatch.setattr(qdrant_store, "_adapter_enabled", lambda: False)
    vector_dir = tmp_path / "vectors"
    vector_dir.mkdir()
    (vector_dir / "meta.jsonl").write_text(
        "\n".join(json.dumps({"doc_id": "d1", "node": i}) for i in (3, 4)),
        encoding="utf-8")
    np.savez_compressed(vector_dir / "vectors.npz",
                        v=np.asarray([[1, 0], [0, 1]], dtype=np.float32))

    result = qdrant_store.sync_from_files(vector_dir, batch_size=1)
    assert result["uploaded"] == 2 and result["dimension"] == 2
    upserts = [call for call in session.calls if call[0] == "put" and "/points" in call[1]]
    assert len(upserts) == 2
    hits = qdrant_store.search(np.asarray([1, 0]), topk=3, minimum=0.2,
                               doc_ids=frozenset({"d1"}))
    assert hits == [("d1", 3, 0.91)]
    body = session.calls[-1][2]
    assert body["filter"]["must"][0]["match"]["any"] == ["d1"]


def test_ping_missing_collection_is_reachable(monkeypatch):
    from lawrag.core.rag import qdrant_store

    session = Session()
    monkeypatch.setattr(qdrant_store, "_session", lambda: session)
    monkeypatch.setattr(qdrant_store, "_adapter_enabled", lambda: False)
    result = qdrant_store.ping()
    assert result["ok"] and not result["ready"] and not result["collection_exists"]
