"""법률 검색기들이 공유하는 조문 좌표·본문 공개 API.

LegalClosure와 평가 스크립트가 termexplore의 private 구현을 직접 호출하지 않도록
조문 root, 본문, 표면 일치, branch 변환을 이 경계로 모은다. 문서 라벨과 질문
참조가 공유하는 의존성 없는 표면 문법은 :mod:`lawrag.core.legal_coordinate`가
소유하며 이 모듈에서도 같은 공개 타입과 파서를 다시 노출한다.
"""

from __future__ import annotations

from lawrag.core.legal_coordinate import (
    LegalCoordinate,
    find_coordinates,
    parse_label,
)
from lawrag.core.rag import termexplore
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index


Coordinate = tuple[str, object]
Branch = termexplore.TermBranch


def article_root(view, node: object) -> object:
    return termexplore.article_root(view, node)


def coordinate_scope(view, node: object) -> str:
    return view.coordinate_scope(article_root(view, node))


def coordinate_key(view, node: object) -> str:
    root = article_root(view, node)
    item = view.by_id.get(root) or {}
    return str(item.get("coordinate_key") or
               f"{view.coordinate_scope(root)}:{item.get('surface') or root}")


def subtree_text(view, node: object, *, cap: int | None = None) -> str:
    return termexplore.exploration.subtree_text(view, node, cap=cap)


def contains_phrase(text: str, phrase: str) -> bool:
    return termexplore.contains_legal_phrase(text, phrase)


def packed(value: str) -> str:
    return termexplore.packed(value)


def article_branch(index: Index, doc_id: str, node: object,
                   terms: tuple[str, ...], *, origin: str,
                   reason: str = "") -> Branch | None:
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    root = article_root(view, node)
    if root not in view.by_id:
        return None
    # canonical Assertion은 내용 해시 doc_id를 가리키므로 법령 개정 뒤 구판 좌표일
    # 수 있다. 같은 법령의 현행본에 동일 조 번호가 있으면 그 좌표로 재결합한다.
    if not index.in_scope(doc_id) and not view.is_current:
        surface = str(view.by_id[root].get("surface") or "").strip()
        rebound = None
        for current_id, current in index.entry_docs.items():
            if current.name != view.name:
                continue
            rebound = next((item.get("id") for item in current.nodes
                            if str(item.get("surface") or "").strip() == surface
                            and current.coordinate_scope(item.get("id")) == "body"), None)
            if rebound is not None:
                doc_id, root = current_id, rebound
                break
        if rebound is None:
            return None
    return termexplore._branch(
        index, doc_id, root, terms, origin=origin, relation_reason=reason)


def branches_from_sections(index: Index, sections: list[Section],
                           terms: tuple[str, ...], *, origin: str) -> list[Branch]:
    out, seen = [], set()
    for section in sections:
        row = article_branch(index, section.doc_id, section.node, terms,
                             origin=origin, reason=section.matched)
        if row is None or row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
    return out


def branches_from_rows(index: Index, items, terms: tuple[str, ...],
                       origin: str) -> list[Branch]:
    """동결 평가 JSON의 좌표 행을 운영과 같은 article branch로 복원한다."""
    out = []
    for item in items or []:
        row = article_branch(
            index, item.get("doc_id"), item.get("node"), terms,
            origin=origin, reason=item.get("path") or "")
        if row is not None:
            out.append(row)
    return out


def merge(cap: int, *groups: list[Branch]) -> list[Branch]:
    out, seen = [], set()
    for group in groups:
        for row in group:
            if row.coordinate in seen:
                continue
            seen.add(row.coordinate)
            out.append(row)
            if len(out) >= max(1, int(cap)):
                return out
    return out
