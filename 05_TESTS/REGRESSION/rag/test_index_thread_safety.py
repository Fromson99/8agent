from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

from lawrag.core.rag import index as index_mod
from lawrag.core.rag.index import Index


def _index() -> Index:
    return Index.from_docs([
        (
            "law-a",
            {"name": "법률 A", "kind": "law", "status": "현행"},
            {
                "nodes": [{
                    "id": 1,
                    "parent": None,
                    "level": 1,
                    "family": "kr_article",
                    "surface": "제1조",
                    "title": "목적",
                    "span": [0, 2],
                }],
                "blocks": [
                    {"idx": 0, "kind": "text", "text": "금융회사는 심사업무를 위탁한다."},
                    {"idx": 1, "kind": "text", "text": "수탁자는 승인 요건을 확인한다."},
                ],
            },
        )
    ])


def test_shared_lazy_postings_are_published_only_after_complete_build(
        monkeypatch) -> None:
    index = _index()
    build_entered = Event()
    reader_entered = Event()
    release_build = Event()
    original = index_mod._lex_terms

    def slow_first_block(text: str) -> list[str]:
        if not build_entered.is_set():
            build_entered.set()
            assert release_build.wait(2)
        return original(text)

    def read_postings() -> dict:
        reader_entered.set()
        return index.postings()

    monkeypatch.setattr(index_mod, "_lex_terms", slow_first_block)
    with ThreadPoolExecutor(max_workers=2) as pool:
        builder = pool.submit(index.postings)
        assert build_entered.wait(1)
        reader = pool.submit(read_postings)
        assert reader_entered.wait(1)
        time.sleep(0.05)
        returned_before_complete = reader.done()
        release_build.set()
        built = builder.result(timeout=2)
        observed = reader.result(timeout=2)

    assert returned_before_complete is False
    assert observed is built
    assert "금융회사는" in built
    assert "수탁자는" in built
    assert index._n_blocks == 2
