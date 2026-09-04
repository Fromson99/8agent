"""자름의 규율 — 폭주 가능한 것만 상한을 두되, 잘리면 표시한다.

실측(구역 p50 80자·최대 68k)이 근거다: 캡 전면 제거는 부칙 전체 같은 부모
구역 하나가 컨텍스트를 터뜨리고, 조용한 캡은 '자료에 없다' 오답을 만든다."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.answer import SECTION_CHARS, assemble          # noqa: E402
from lawrag.core.rag.index import Index                             # noqa: E402
from lawrag.core.rag.search import Hit, SearchResult                # noqa: E402


def _doc(block_chars: int):
    blocks = [{"idx": i, "page": 1, "text": "가" * block_chars, "kind": "text"}
              for i in range(3)]
    return ("d1", {"name": "LONG.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "긴 조문", "page": 1, "span": [0, 3]},
    ], "blocks": blocks})


def test_잘리면_표시한다():
    v = Index.from_docs([_doc(3000)]).docs["d1"]              # 9000자 > cap
    text = v.section_text(v.by_id[1], cap=6000)
    assert text.endswith("…(구역이 길어 여기서 잘림 — 이후 내용 있음)")
    assert len(text) <= 6000 + 40                             # 상한은 지킨다


def test_안_잘리면_표시가_없다():
    v = Index.from_docs([_doc(100)]).docs["d1"]               # 300자 < cap
    text = v.section_text(v.by_id[1], cap=6000)
    assert "잘림" not in text and text.count("가") == 300


def test_회수_본문도_같은_규율():
    idx = Index.from_docs([_doc(SECTION_CHARS)])              # 확실히 넘긴다
    hit = Hit(target="doc:d1:1", kind="제목", value="긴 조문", score=1.0,
              match="정확", doc_id="d1", doc="LONG.pdf", node=1)
    sections = assemble(idx, SearchResult(query="긴 조문", mode="정확",
                                          hits=[hit], ladder=[]))
    assert sections[0].text.endswith("…(구역이 길어 여기서 잘림 — 이후 내용 있음)")
