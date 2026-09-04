"""A+B+C+Verifier 근거가 부족할 때만 여는 질문-grounded 관계 폐쇄.

일반적인 주변 조문은 답변 입력을 키우므로, 법적으로 필수인 관계이면서 질문 용어가
target 본문에 다시 나타나거나 실제 누락된 규범요건을 채우는 후보만 최대 소수 보충한다.
"""

from __future__ import annotations

from collections import Counter
import re

from lawrag.core.domain_graph import requirements
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag.index import Index


DEFAULT_CAP = 1
_FAMILY_SUFFIXES = ("시행규칙", "시행령", "시행세칙")
_COMPARISON_OR_EXISTENCE = re.compile(r"있는가|없는가|에도|여부|차이|비교|동일")
_DOCUMENT_EVIDENCE = re.compile(r"서류|제출|보고서|신청서|첨부")


def document_family(view) -> str:
    name = re.sub(r"[\s·ㆍ]+", "", view.name)
    name = re.split(r"[_\[(]", name, maxsplit=1)[0]
    for suffix in _FAMILY_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[:-len(suffix)]
            break
    return f"{view.folder or view.scope_kind}:{name}"


def _present_kinds(index: Index, rows) -> set[str]:
    present = set()
    for row in rows:
        text = coordinates.subtree_text(
            index.docs[row.doc_id], row.node, cap=None)
        present.update(item.kind for item in requirements.extract(text))
    return present


def select(index: Index, question: str, base: list[coordinates.Branch],
           candidates: list[coordinates.Branch], *, cap: int = DEFAULT_CAP) \
        -> tuple[list[coordinates.Branch], dict]:
    """필수+질문근거 또는 누락요건 충족 후보만 문서군 일관성 순으로 선택한다."""
    requested = set(requirements.requested_kinds(question))
    present = _present_kinds(index, base)
    missing = requested - present
    if any(row.origin == "normative-reference-verifier" for row in base):
        return [], {
            "strategy": "mandatory-and-query-grounded-or-missing-requirement",
            "cap": cap, "requested_kinds": sorted(requested),
            "present_kinds": sorted(present), "missing_kinds": sorted(missing),
            "candidate_count": len(candidates), "eligible_count": 0,
            "selected": [], "candidates": [],
            "fallback": "verified_reference_already_closes_relation_need",
        }
    seen = {row.coordinate for row in base}
    doc_counts = Counter(row.doc_id for row in base)
    family_counts = Counter(document_family(index.docs[row.doc_id]) for row in base)
    eligible = []
    audit_candidates = []
    asks_comparison = bool(_COMPARISON_OR_EXISTENCE.search(question or ""))
    asks_document_evidence = bool(_DOCUMENT_EVIDENCE.search(question or ""))
    wants_form = any(token in question for token in (
        "서식", "서류", "첨부", "제출", "보고서", "신청서"))
    for row in candidates:
        if row.coordinate in seen:
            continue
        view = index.docs[row.doc_id]
        if (not wants_form
                and (view.scope_kind == "서식" or "별표·서식" in row.path)):
            continue
        text = coordinates.subtree_text(
            view, row.node, cap=None)
        kinds = {item.kind for item in requirements.extract(text)}
        fills = tuple(sorted(missing & kinds))
        grounded_terms = tuple(dict.fromkeys(row.terms))
        # mandatory만으로는 정의·별표·다른 시장의 근거 조문이 대량 유입된다.
        # 질문 원문이 target에서 다시 확인되거나 실제 요건 결손을 채워야 한다.
        comparison_support = asks_comparison and len(grounded_terms) >= 2
        allowed = (asks_document_evidence or bool(fills)
                   or bool(row.mandatory and grounded_terms)
                   or comparison_support)
        family = document_family(view)
        score = (
            len(fills),
            int(row.mandatory),
            int(comparison_support),
            doc_counts[row.doc_id],
            family_counts[family],
            len(grounded_terms),
            max((len(coordinates.packed(term)) for term in grounded_terms), default=0),
        )
        public = {
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "mandatory": row.mandatory,
            "terms": list(grounded_terms), "fills": list(fills),
            "comparison_support": comparison_support,
            "same_doc_count": doc_counts[row.doc_id],
            "same_family_count": family_counts[family],
            "eligible": allowed, "score": list(score),
        }
        audit_candidates.append(public)
        if allowed:
            eligible.append((score, row, public))
    if asks_document_evidence:
        # 제출범위 질문은 여러 시장·문서의 적용 범위를 함께 읽어야 하므로 기존
        # 관계 순서를 보존한다. 이 유형에만 넓은 cap을 허용한다.
        selected = [row for _score, row, _public in eligible[:6]]
        effective_cap = 6
    else:
        eligible.sort(key=lambda item: (
            *(-value for value in item[0]), item[1].doc, item[1].path))
        selected = [row for _score, row, _public in eligible[:max(0, int(cap))]]
        effective_cap = cap
    selected_coordinates = {row.coordinate for row in selected}
    return selected, {
        "strategy": "mandatory-and-query-grounded-or-missing-requirement",
        "cap": effective_cap, "requested_kinds": sorted(requested),
        "asks_comparison_or_existence": asks_comparison,
        "asks_document_evidence": asks_document_evidence,
        "present_kinds": sorted(present), "missing_kinds": sorted(missing),
        "candidate_count": len(candidates), "eligible_count": len(eligible),
        "selected": [row for row in audit_candidates
                     if (row["doc_id"], row["node"]) in selected_coordinates],
        "candidates": audit_candidates,
    }
