"""LegalClosure 내부 감사 구조를 안정적인 API 응답으로 접는다."""

from __future__ import annotations


def public_meta(meta: dict) -> dict:
    primary = meta.get("primary") or {}
    assertion = meta.get("assertion") or {}
    keyword = meta.get("keyword") or {}
    annotations = meta.get("legal_annotations") or {}
    ontology = meta.get("ontology_rag") or {}
    result = {
        "strategy": meta.get("strategy"), "cap": meta.get("cap"),
        "runtime": meta.get("runtime") or {},
        "primary": {
            "strategy": primary.get("strategy"),
            "term_plan": primary.get("term_plan") or {},
            "candidate_branches": primary.get("candidate_branches", 0),
            "selection_calls": primary.get("selection_calls", 0),
            "selected": primary.get("selected") or [],
        },
        "assertion": {
            "strategy": assertion.get("strategy"),
            "candidate_ranges": assertion.get("candidate_ranges", 0),
            "document_route": assertion.get("document_route") or {},
            "tree": assertion.get("tree") or {},
            "fallback": assertion.get("fallback") or "",
            "shortcut": assertion.get("shortcut") or {},
            "selected": assertion.get("selected") or [],
        },
        "keyword": {
            "keywords": keyword.get("keywords") or [],
            "unmatched": keyword.get("unmatched") or [],
            "block_hits": keyword.get("block_hits", 0),
            "article_candidates": keyword.get("article_candidates") or [],
        },
        "expansion": meta.get("expansion") or {},
        "feedback_loop": meta.get("feedback_loop") or {
            "enabled": False, "ran": False,
        },
        "reference_verifier": meta.get("reference_verifier") or {},
        "legal_graph": meta.get("legal_graph") or {
            "enabled": False, "status": "disabled", "added_count": 0,
        },
        "ontology_rag": {
            key: ontology.get(key)
            for key in (
                "schema_version", "profile_id", "status", "reason", "detail",
                "fallback", "projection_id", "matched_surface", "clause_span_ids",
                "canonical_evidence_ids", "rule_ids", "baseline_count",
                "final_count", "added_count", "added_coordinates",
                "baseline_floor_preserved", "direct_conclusion_allowed",
                "quality_status", "definition_generation",
                "definition_content_sha256", "graph_generation",
                "graph_content_sha256", "store_binding", "knowledge_cache",
                "knowledge_cache_key_sha256",
            )
            if key in ontology
        },
        "legal_annotations": {
            "requested_kinds": annotations.get("requested_kinds") or [],
            "as_of": annotations.get("as_of") or "",
            "warnings": annotations.get("warnings") or [],
            "row_count": len(annotations.get("rows") or []),
        },
        "closure": meta.get("closure") or [],
        "selected": meta.get("selected") or [],
    }
    # The semantic annotation rows stay private, but their immutable source
    # coordinates must survive the API presentation boundary.
    provenance_rows = [
        {"doc_id": row.get("doc_id"), "node": row.get("node"),
         "content_provenance": row.get("content_provenance")}
        for row in annotations.get("rows") or []
        if row.get("content_provenance") is not None
    ]
    if provenance_rows:
        result["legal_annotations"]["content_provenance"] = provenance_rows
    if meta.get("content_snapshot") is not None:
        result["content_snapshot"] = meta["content_snapshot"]
    return result


def ladder(meta: dict, final_count: int) -> list[dict]:
    rows = [
        {"stage": "정확 구조", "count": len(meta["primary"]["selected"]),
         "note": "명시 좌표·대상어 교집합·직접 근거 (상한 12)"},
        {"stage": "Assertion 구조", "count": len(meta["assertion"]["selected"]),
         "note": "canonical 문서군→문서→조문 닫힌 메뉴 (상한 8)"},
        {"stage": "균등 BM25", "count": len(meta["keyword"]["article_candidates"]),
         "note": "검색어별 quota 보충 (상한 8)"},
        {"stage": "직접 관계 폐쇄", "count": len(meta["closure"]),
         "note": "인용·피인용·필수 법률관계 한 층 (상한 6)"},
        {"stage": "규범기능 참조 검증",
         "count": len(meta["reference_verifier"].get("selected") or []),
         "note": "준용·위임 질문의 고유 표제 참조만 남는 자리에서 보충"},
        {"stage": "LegalClosure", "count": final_count,
         "note": "조문 좌표 중복 제거 · 최종 상한 20"},
    ]
    feedback = meta.get("feedback_loop") or {}
    if feedback.get("ran"):
        rows.insert(-1, {
            "stage": "부족 재탐색",
            "count": len(feedback.get("selected") or []),
            "note": (f"관계·구조·키워드·벡터 점프 {feedback.get('steps', 0)}걸음 · "
                     f"충분성={'충족' if feedback.get('sufficient') else '미충족'}"),
        })
    graph = meta.get("legal_graph") or {}
    if graph.get("enabled"):
        rows.insert(-1, {
            "stage": "Legal Graph 조건부 폐쇄",
            "count": int(graph.get("added_count") or 0),
            "note": (
                f"{graph.get('status', '')} · query family×exact source "
                f"· generation {str(graph.get('generation_id') or '')[:18]}"
            ),
        })
    return rows
