"""구조화 산출(Document) → 검색 색인 — 에이전트가 검색 사다리를 빌려 쓰는 다리.

이 저장소에는 구조화가 둘 있다. 뷰어·RAG 는 형식 무관 해석(core.structure)의
nodes/blocks 를 읽고, agent1 은 형식 주도 구조화(core.structurize)의 sections
를 읽는다. 검색 사다리(core.rag.search)는 앞의 모양만 안다 — 이 모듈이 뒤의
모양을 앞의 모양으로 편다.

좌표를 잃지 않는 것이 전부다. 사다리의 히트는 node 번호로 돌아오고, 그 번호가
어느 section_id 였는지는 여기서 만든 대응표(sec_of)가 되돌린다 — 대응표 없이
색인만 만들면 "찾았다"까지만 알고 어느 구역인지 되짚을 수 없다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.rag.index import Index

if TYPE_CHECKING:                      # 실행 시 의존을 만들지 않는다 — 타입만
    from core.structurize import Document


def view_of(doc: "Document", doc_id: str = "doc") -> tuple[dict, dict, dict]:
    """(meta, result, sec_of) — Index.from_docs 가 받는 모양과 좌표 대응표.

    구역 하나가 마디 하나다. 구역의 content 를 순서대로 블록으로 펴고, 마디의
    span 이 그 범위를 가리킨다. 내용 없는 구역(자식이 내용을 드는 부모)은 span
    이 비어 다음 블록 하나를 주인 계산에서 스칠 수 있는데, 자식이 더 깊어서
    이기므로 실제로는 자식 소유가 유지된다 — 같은 깊이의 빈 형제만 예외이고,
    그때도 이웃 구역으로 빗나갈 뿐 좌표가 사라지지는 않는다.
    """
    blocks: list[dict] = []
    nodes: list[dict] = []
    sec_of: dict[int, str] = {}

    for si, sec in enumerate(doc.sections, start=1):
        start = len(blocks)
        for item in sec.content:
            if item.get("type") == "table":
                text = " ".join(c.get("text", "")
                                for c in item.get("cells", {}).get("cells", []))
                kind = "table"
            else:
                text = item.get("text") or ""
                kind = "text"
            blocks.append({"idx": len(blocks), "page": item.get("page", 1),
                           "text": text, "kind": kind})
        page = (sec.pages[0] if sec.pages
                else blocks[start]["page"] if len(blocks) > start else 1)
        nodes.append({"id": si, "parent": None, "level": sec.level,
                      "surface": "",
                      "title": sec.path[-1] if sec.path else sec.section_id,
                      "page": page, "span": [start, len(blocks)]})
        sec_of[si] = sec.section_id

    by_sec = {sec.section_id: i for i, sec in enumerate(doc.sections, start=1)}
    for i, sec in enumerate(doc.sections, start=1):
        if sec.parent and sec.parent in by_sec:
            nodes[i - 1]["parent"] = by_sec[sec.parent]

    return ({"name": doc.source_file}, {"nodes": nodes, "blocks": blocks}, sec_of)


def index_of(doc: "Document", doc_id: str = "doc") -> tuple[Index, dict[int, str]]:
    """문서 하나짜리 색인. 문서 안에서 찾는 용도라 저장소를 거치지 않는다."""
    meta, result, sec_of = view_of(doc, doc_id)
    return Index.from_docs([(doc_id, meta, result)]), sec_of
