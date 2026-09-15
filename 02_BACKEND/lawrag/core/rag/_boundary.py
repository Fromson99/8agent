"""Declared ownership for the compatibility modules in :mod:`lawrag.core.rag`."""

from __future__ import annotations

from importlib import import_module


MODULE_OWNERS = {
    "retrieval": frozenset({
        "article_reachability", "assertionfirst", "bench", "combinations",
        "companion_recovery", "conceptfirst", "definitions", "expand",
        "exploration", "framequery", "general_search", "index", "landings",
        "latent_discovery_pool", "oql", "proof_basis_augmenting",
        "proof_basis_exchange", "provider_compatible_span_selector", "qdrant_store",
        "query_grounding", "queryguide", "raw_evidence_selection", "recover",
        "recover_domains", "relation_navigation", "scopes", "search",
        "source_registry_admission", "tags", "termexplore", "termretrieve",
        "vecfirst", "vector", "verified_span_coverage_gate", "verified_span_selector",
    }),
    "evidence": frozenset({
        "assertion_shortcuts", "claim_citation_selector", "delegation",
        "evidence_confusion", "evidence_slot_nondropping", "frames", "graph",
        "grounded_witness", "legal_coordinates", "legal_evidence",
        "legal_graph_store", "legal_references", "legal_validity", "lexicon",
        "refs", "relations", "taxonomy",
    }),
    "reasoning": frozenset({
        "answer", "claimwise_nondestructive_compiler", "compare", "evaluation",
        "internal_compliance", "judge", "legal_answer_checklists",
        "legal_conditional_closure", "legal_graph_closure", "legal_proposition_compiler",
        "legal_semantic_search", "legalclosure", "legalclosure_runtime", "legalissue",
        "proposition_assessment_shadow", "query_family_runtime", "selective_legal_guide",
    }),
    "knowledge": frozenset({
        "approvals", "audit", "controls", "induce", "promote",
        "proof_boundary_feedback", "recall_first_feedback", "replay",
        "retrieval_feedback", "rules", "search_trace", "span_feedback", "switches",
        "term_proposals", "tuples", "verdicts", "wikictx", "wikiledger", "wikilife",
    }),
}


def owned_modules(owner: str) -> frozenset[str]:
    try:
        return MODULE_OWNERS[owner]
    except KeyError as exc:
        raise ValueError(f"unknown RAG boundary: {owner}") from exc


def load_owned(owner: str, name: str):
    if name not in owned_modules(owner):
        raise AttributeError(name)
    return import_module(f"lawrag.core.rag.{name}")

