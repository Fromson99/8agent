"""규칙 시험의 안전 반경 — **재해석해도 되는 문서만** 만진다.

custom 규칙은 문서를 안 가려서, 시험은 영향받는 문서를 전부 다시 해석해
전후를 재야 한다. 그런데 재해석은 PDF 추론 경로다:

    parse.json 있음   docling 이 파싱한 문서 — 규칙이 여기 든다. 캐시라 빠르고
                      결과도 결정론이다. 시험 범위.
    parse.json 없음   lawxml·XML 인제스트 — 계층이 원천 태그에서 왔다. 규칙과
                      무관하고, 재해석하면 합성 PDF 를 docling 이 다시 추론해
                      **원천 태그 구조가 사라진다**. 절대 건드리면 안 된다.

이 시험은 그 경계를 못 박는다 — 여기가 무너지면 법령 문서의 계층이 통째로
날아간다(되돌릴 방법은 XML 재인제스트뿐이다).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def _doc(store: Path, doc_id: str, *, parsed: bool) -> None:
    d = store / doc_id
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"nodes": [], "blocks": []}),
                                   encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"name": doc_id, "score": 0.5}),
                                 encoding="utf-8")
    (d / "source.pdf").write_bytes(b"%PDF-1.4\n")
    if parsed:
        (d / "parse.json").write_text("{}", encoding="utf-8")


def test_규칙_시험은_파싱캐시가_있는_문서만_만진다(tmp_path, monkeypatch):
    store = tmp_path / "structure"
    store.mkdir()
    pdf_doc = "a" * 16          # docling 파싱 산출 — 규칙이 닿는다
    xml_doc = "b" * 16          # lawxml 인제스트 — 재해석하면 태그가 사라진다
    _doc(store, pdf_doc, parsed=True)
    _doc(store, xml_doc, parsed=False)

    monkeypatch.setenv("STRUCTURE_STORE", str(store))
    from api.routers import structure as mod
    importlib.reload(mod)                      # STORE 는 모듈 적재 때 정해진다

    assert mod._rule_scope() == [pdf_doc]      # XML 문서는 범위 밖
    assert set(mod._all_doc_ids()) == {pdf_doc, xml_doc}   # 목록에는 보인다
    assert xml_doc not in mod._rule_scope()
