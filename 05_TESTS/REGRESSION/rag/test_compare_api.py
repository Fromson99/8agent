"""내규↔외규 비교 API의 입력 문서 경계."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from lawrag.api.routers import rag
from lawrag.core.rag.index import Index


def _index(kind: str) -> Index:
    return Index.from_docs([(
        "d1", {"name": "테스트규정", "kind": kind},
        {"nodes": [{"id": 1, "parent": None, "level": 0,
                    "surface": "제1조", "title": "목적", "page": 1,
                    "span": [0, 1]}],
         "blocks": [{"idx": 0, "page": 1, "text": "목적 조문", "kind": "text"}]},
    )])


def test_compare_api_rejects_external_document_as_fact_side(monkeypatch):
    monkeypatch.setattr(rag.index_mod, "current", lambda: _index("law"))

    with pytest.raises(HTTPException) as caught:
        rag.rag_compare(rag.Compare(doc="테스트규정", article="제1조"))

    assert caught.value.status_code == 400
    assert "내규 문서" in str(caught.value.detail)
