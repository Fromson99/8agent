#!/usr/bin/env python3
"""Deterministic full audit of frozen golden coordinates against legal data stores.

This runner is scoped to ADR-0082.  It does not call retrieval or an LLM and does
not mutate any source dataset.  Its JSON output is stable for identical inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CM_PATH = ROOT / "data/review/cm_core_e2e_v1.json"
FSC_PATH = ROOT / "data/review/fsc_hard_retrieval_v1.json"
LAW_INDEX_PATH = ROOT / "data/law_index.json"
STRUCTURE_ROOT = ROOT / "data/structure"
GRAPH_PATH = ROOT / "data/domain_graph/graph.sqlite"
AUDIT_DATE = "20260827"
EXPECTED_COMBINED_SHA256 = (
    "9efd698528a7f7db36d8c5b26e470adb500e0b4d4b0e25cc4a18e5fc9ea9869e"
)

ARTICLE_RE = re.compile(r"제\s*(\d+)(?:-(\d+))?\s*조(?:\s*의\s*(\d+))?")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def combined_dataset_sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compact_date(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def canonical_article(value: object) -> str:
    match = ARTICLE_RE.search(str(value or ""))
    if not match:
        return str(value or "").replace(" ", "")
    base, hyphen, suffix = match.groups()
    if hyphen:
        return f"제{base}-{hyphen}조" + (f"의{suffix}" if suffix else "")
    if suffix:
        return f"제{base}조의{suffix}"
    return f"제{base}조"


def is_in_appendix(node: dict[str, Any], node_by_id: dict[int, dict[str, Any]]) -> bool:
    current: dict[str, Any] | None = node
    while current:
        if current.get("family") == "buchik" or current.get("surface") == "부칙":
            return True
        current = node_by_id.get(current.get("parent"))
    return False


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def article_text(result: dict[str, Any], node: dict[str, Any]) -> str:
    blocks = result.get("blocks") or []
    span = node.get("span") or []
    if len(span) != 2 or not all(isinstance(v, int) for v in span):
        return ""
    start, end = span
    if start < 0 or end < start or end > len(blocks):
        return ""
    return "\n".join(str(block.get("text") or "") for block in blocks[start:end])


def make_issue(
    category: str,
    severity: str,
    scope: str,
    message: str,
    **evidence: object,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "scope": scope,
        "message": message,
        "evidence": evidence,
    }


def discover_structure() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    documents: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for folder in sorted(path for path in STRUCTURE_ROOT.iterdir() if path.is_dir()):
        meta_path = folder / "meta.json"
        result_path = folder / "result.json"
        scope = f"structure:{folder.name}"
        if not meta_path.exists() or not result_path.exists():
            issues.append(make_issue(
                "structure_file_missing", "fatal", scope,
                "Document directory lacks meta.json or result.json",
                meta_exists=meta_path.exists(), result_exists=result_path.exists(),
            ))
            continue
        try:
            meta = load_json(meta_path)
            result = load_json(result_path)
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(make_issue(
                "structure_parse_error", "fatal", scope,
                "Document JSON could not be parsed", error=str(exc),
            ))
            continue

        doc_id = str(meta.get("doc_id") or "")
        if doc_id != folder.name:
            issues.append(make_issue(
                "structure_doc_id_mismatch", "fatal", scope,
                "Folder name and meta doc_id differ",
                folder=folder.name, meta_doc_id=doc_id,
            ))

        nodes = result.get("nodes") or []
        blocks = result.get("blocks") or []
        node_by_id: dict[int, dict[str, Any]] = {}
        article_by_surface: dict[str, list[dict[str, Any]]] = defaultdict(list)
        duplicate_node_ids: list[int] = []
        bad_parents: list[dict[str, Any]] = []
        bad_spans: list[dict[str, Any]] = []
        bad_blocks: list[dict[str, Any]] = []

        for node in nodes:
            node_id = node.get("id")
            if not isinstance(node_id, int):
                continue
            if node_id in node_by_id:
                duplicate_node_ids.append(node_id)
            node_by_id[node_id] = node
            if node.get("family") == "kr_article":
                article_by_surface[canonical_article(node.get("surface"))].append(node)

        for node in nodes:
            node_id = node.get("id")
            parent = node.get("parent")
            if parent is not None and parent not in node_by_id:
                bad_parents.append({"node": node_id, "parent": parent})
            block = node.get("block")
            if not isinstance(block, int) or block < 0 or block >= len(blocks):
                bad_blocks.append({"node": node_id, "block": block})
            span = node.get("span")
            if (not isinstance(span, list) or len(span) != 2
                    or not all(isinstance(v, int) for v in span)
                    or span[0] < 0 or span[1] < span[0] or span[1] > len(blocks)):
                bad_spans.append({"node": node_id, "span": span})

        if duplicate_node_ids:
            issues.append(make_issue(
                "duplicate_node_id", "fatal", scope, "Duplicate node IDs found",
                node_ids=sorted(set(duplicate_node_ids)),
            ))
        if bad_parents:
            issues.append(make_issue(
                "orphan_node_parent", "fatal", scope, "Nodes reference absent parents",
                samples=bad_parents[:20], count=len(bad_parents),
            ))
        if bad_spans:
            issues.append(make_issue(
                "invalid_node_span", "fatal", scope, "Nodes contain invalid block spans",
                samples=bad_spans[:20], count=len(bad_spans),
            ))
        if bad_blocks:
            issues.append(make_issue(
                "invalid_node_block", "fatal", scope, "Nodes reference absent blocks",
                samples=bad_blocks[:20], count=len(bad_blocks),
            ))

        duplicate_articles = {
            surface: [int(node["id"]) for node in article_nodes]
            for surface, article_nodes in article_by_surface.items()
            if len([node for node in article_nodes if not is_in_appendix(node, node_by_id)]) > 1
        }
        if duplicate_articles:
            issues.append(make_issue(
                "duplicate_article_surface", "warning", scope,
                "Multiple kr_article nodes have the same normalized article surface",
                articles=duplicate_articles,
            ))

        documents[folder.name] = {
            "meta": meta,
            "result": result,
            "node_by_id": node_by_id,
            "article_by_surface": dict(article_by_surface),
            "counts": {
                "nodes": len(nodes),
                "blocks": len(blocks),
                "articles": sum(len(value) for value in article_by_surface.values()),
            },
        }
    return documents, issues


def graph_audit() -> tuple[set[str], dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    section_ids: set[str] = set()
    summary: dict[str, Any] = {"available": GRAPH_PATH.exists()}
    if not GRAPH_PATH.exists():
        issues.append(make_issue(
            "graph_missing", "fatal", "graph", "graph.sqlite is absent",
            path=str(GRAPH_PATH.relative_to(ROOT)),
        ))
        return section_ids, summary, issues
    try:
        connection = sqlite3.connect(f"file:{GRAPH_PATH}?mode=ro", uri=True)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        node_count = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        section_ids = {
            row[0] for row in connection.execute(
                "SELECT id FROM nodes WHERE kind = 'Section'"
            )
        }
        orphan_src = connection.execute(
            "SELECT COUNT(*) FROM edges e LEFT JOIN nodes n ON n.id=e.src WHERE n.id IS NULL"
        ).fetchone()[0]
        orphan_dst = connection.execute(
            "SELECT COUNT(*) FROM edges e LEFT JOIN nodes n ON n.id=e.dst WHERE n.id IS NULL"
        ).fetchone()[0]
        summary.update({
            "integrity_check": integrity,
            "nodes": node_count,
            "sections": len(section_ids),
            "edges": edge_count,
            "orphan_edge_sources": orphan_src,
            "orphan_edge_destinations": orphan_dst,
        })
        if integrity != "ok" or orphan_src or orphan_dst:
            issues.append(make_issue(
                "graph_integrity", "fatal", "graph",
                "SQLite or edge endpoint integrity failed", **summary,
            ))
    except sqlite3.Error as exc:
        issues.append(make_issue(
            "graph_parse_error", "fatal", "graph",
            "graph.sqlite could not be audited", error=str(exc),
        ))
    finally:
        if "connection" in locals():
            connection.close()
    return section_ids, summary, issues


def index_audit(
    law_index: dict[str, Any],
    documents: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    docs = law_index.get("docs") or []
    index_by_name: dict[str, dict[str, Any]] = {}
    name_counts = Counter(str(row.get("name") or "") for row in docs)
    for row in docs:
        name = str(row.get("name") or "")
        doc_id = str(row.get("doc_id") or "")
        if name in index_by_name:
            continue
        index_by_name[name] = row
        scope = f"law_index:{name}"
        document = documents.get(doc_id)
        if not document:
            issues.append(make_issue(
                "index_document_missing", "fatal", scope,
                "law_index points to a missing structure document", doc_id=doc_id,
            ))
            continue
        meta = document["meta"]
        if str(meta.get("name") or "") != name:
            issues.append(make_issue(
                "index_name_mismatch", "fatal", scope,
                "law_index name differs from structure meta",
                index_name=name, meta_name=meta.get("name"), doc_id=doc_id,
            ))
        if compact_date(meta.get("enforce")) != compact_date(row.get("enforce")):
            issues.append(make_issue(
                "index_enforcement_mismatch", "fatal", scope,
                "law_index enforcement differs from structure meta",
                index_enforce=row.get("enforce"), meta_enforce=meta.get("enforce"), doc_id=doc_id,
            ))
        if str(meta.get("status") or "") not in {"현행", ""}:
            issues.append(make_issue(
                "index_selected_noncurrent_status", "metadata_conflict", scope,
                "law_index selects a document whose structure status is not 현행",
                doc_id=doc_id, status=meta.get("status"), enforce=meta.get("enforce"),
            ))

    for name, count in sorted(name_counts.items()):
        if count > 1:
            issues.append(make_issue(
                "duplicate_law_index_name", "fatal", f"law_index:{name}",
                "law_index contains duplicate document names", count=count,
            ))

    selected_ids = {str(row.get("doc_id") or "") for row in docs}
    for doc_id, document in sorted(documents.items()):
        meta = document["meta"]
        same_name = index_by_name.get(str(meta.get("name") or ""))
        if (str(meta.get("status") or "") == "현행" and doc_id not in selected_ids
                and same_name):
            issues.append(make_issue(
                "unselected_current_status", "metadata_conflict", f"structure:{doc_id}",
                "Structure document is marked 현행 but law_index does not select it",
                name=meta.get("name"), enforce=meta.get("enforce"), revised=meta.get("revised"),
                law_index_doc_id=(same_name or {}).get("doc_id"),
                law_index_enforce=(same_name or {}).get("enforce"),
            ))

            selected = documents.get(str(same_name.get("doc_id") or ""))
            if selected:
                selected_surfaces = set(selected["article_by_surface"])
                alternate_surfaces = set(document["article_by_surface"])
                missing_from_index = sorted(alternate_surfaces - selected_surfaces)
                missing_from_status_current = sorted(selected_surfaces - alternate_surfaces)
                changed_same_surface: list[str] = []
                for surface in sorted(selected_surfaces & alternate_surfaces):
                    selected_nodes = selected["article_by_surface"][surface]
                    alternate_nodes = document["article_by_surface"][surface]
                    if len(selected_nodes) != 1 or len(alternate_nodes) != 1:
                        continue
                    selected_text = normalized_text(article_text(selected["result"], selected_nodes[0]))
                    alternate_text = normalized_text(article_text(document["result"], alternate_nodes[0]))
                    if selected_text != alternate_text:
                        changed_same_surface.append(surface)
                issues.append(make_issue(
                    "law_version_composition_conflict", "metadata_conflict",
                    f"law_version:{meta.get('name')}",
                    "law_index-selected and status-current documents contain different article sets or texts",
                    law_index_doc_id=same_name.get("doc_id"),
                    law_index_enforce=same_name.get("enforce"),
                    law_index_status=selected["meta"].get("status"),
                    status_current_doc_id=doc_id,
                    status_current_enforce=meta.get("enforce"),
                    missing_from_law_index=missing_from_index,
                    missing_from_status_current=missing_from_status_current,
                    changed_same_surface_count=len(changed_same_surface),
                    changed_same_surface=changed_same_surface,
                ))
    return index_by_name, issues


def find_reference_article_candidates(
    answer: str,
    expected_articles: list[dict[str, Any]],
) -> dict[str, Any]:
    mentioned = sorted({canonical_article(match.group(0)) for match in ARTICLE_RE.finditer(answer)})
    expected = sorted({canonical_article(item.get("article")) for item in expected_articles})
    missing = sorted(set(mentioned) - set(expected))
    return {
        "mentioned_article_surfaces": mentioned,
        "expected_article_surfaces": expected,
        "uncovered_article_surfaces": missing,
        "review_required": bool(missing),
        "limitation": (
            "Article-number-only heuristic; aliases and multiple laws can make an uncovered surface "
            "a false positive. It is not an automatic gold error."
        ),
    }


def source_provenance_audit(
    cm: dict[str, Any], fsc: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    cm_source = cm.get("source") or {}
    cm_path = ROOT / str(cm_source.get("path") or "")
    cm_exists = cm_path.is_file()
    cm_actual_sha = file_sha256(cm_path) if cm_exists else None
    cm_expected_sha = str(cm_source.get("sha256") or "")
    if not cm_exists or cm_actual_sha != cm_expected_sha:
        issues.append(make_issue(
            "cm_source_provenance", "fatal", "source:cm",
            "CM source DOCX is missing or its hash differs",
            path=str(cm_path.relative_to(ROOT)), exists=cm_exists,
            expected_sha256=cm_expected_sha, actual_sha256=cm_actual_sha,
        ))

    fsc_rows: list[dict[str, Any]] = []
    for case in fsc.get("cases") or []:
        case_id = str(case.get("id") or "")
        source_path = ROOT / str(case.get("source_file") or "")
        exists = source_path.is_file()
        actual_sha = file_sha256(source_path) if exists else None
        expected_sha = str(case.get("source_sha256") or "")
        valid = bool(exists and actual_sha == expected_sha)
        fsc_rows.append({
            "case_id": case_id,
            "path": str(case.get("source_file") or ""),
            "exists": exists,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "valid": valid,
        })
        if not valid:
            issues.append(make_issue(
                "fsc_source_provenance", "fatal", f"source:{case_id}",
                "FSC raw source is missing or its hash differs",
                **fsc_rows[-1],
            ))
    return {
        "cm": {
            "path": str(cm_source.get("path") or ""),
            "exists": cm_exists,
            "expected_sha256": cm_expected_sha,
            "actual_sha256": cm_actual_sha,
            "valid": bool(cm_exists and cm_actual_sha == cm_expected_sha),
        },
        "fsc": {
            "cases": len(fsc_rows),
            "valid_cases": sum(row["valid"] for row in fsc_rows),
            "rows": fsc_rows,
        },
    }, issues


def audit_gold(
    suites: list[tuple[str, dict[str, Any]]],
    documents: dict[str, dict[str, Any]],
    index_by_name: dict[str, dict[str, Any]],
    graph_sections: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    coordinate_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()

    current_articles: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for current_doc_id, current_document in sorted(documents.items()):
        current_meta = current_document["meta"]
        if str(current_meta.get("status") or "").strip() == "구판":
            continue
        for surface, nodes in current_document["article_by_surface"].items():
            for current_node in nodes:
                if is_in_appendix(current_node, current_document["node_by_id"]):
                    continue
                current_articles[(str(current_meta.get("name") or ""), surface)].append({
                    "doc_id": current_doc_id,
                    "node": current_node.get("id"),
                })

    for suite_name, suite in suites:
        source_date = compact_date((suite.get("source") or {}).get("date_from_filename"))
        for case in suite.get("cases") or []:
            case_id = str(case.get("id") or "")
            case_scope = f"gold:{case_id}"
            if case_id in seen_case_ids:
                issues.append(make_issue(
                    "duplicate_case_id", "fatal", case_scope,
                    "Case ID appears more than once across frozen suites", suite=suite_name,
                ))
            seen_case_ids.add(case_id)

            answer = str(case.get("reference_answer") or "")
            expected_articles = case.get("expected_articles") or []
            declared_answer_hash = str(case.get("reference_sha256") or "")
            actual_answer_hash = sha256_bytes(
                (str(case.get("source_question") or "") + "\n" + answer).encode("utf-8")
            )
            if declared_answer_hash and declared_answer_hash != actual_answer_hash:
                issues.append(make_issue(
                    "reference_answer_hash_mismatch", "fatal", case_scope,
                    "reference_sha256 does not match reference_answer UTF-8 bytes",
                    declared=declared_answer_hash, actual=actual_answer_hash,
                ))

            published = compact_date(case.get("published")) or source_date
            reference_review = find_reference_article_candidates(answer, expected_articles)
            if reference_review["review_required"]:
                issues.append(make_issue(
                    "reference_article_not_in_expected", "gold_completeness_review", case_scope,
                    "Reference answer mentions article surfaces absent from expected_articles",
                    uncovered=reference_review["uncovered_article_surfaces"],
                    expected=reference_review["expected_article_surfaces"],
                ))

            case_hard_pass = True
            case_version_drift = False
            current_statuses: list[str] = []
            case_coord_start = len(coordinate_rows)
            for ordinal, gold in enumerate(expected_articles, start=1):
                doc_id = str(gold.get("doc_id") or "")
                node_raw = gold.get("node")
                node_id = int(node_raw) if str(node_raw).isdigit() else None
                law = str(gold.get("law") or "")
                article = canonical_article(gold.get("article"))
                scope = f"gold:{case_id}:{ordinal}:{doc_id}:{node_raw}"
                checks: dict[str, bool] = {}
                row_issues: list[str] = []

                document = documents.get(doc_id)
                checks["document_exists"] = document is not None
                if not document:
                    row_issues.append("gold_document_missing")
                    issues.append(make_issue(
                        "gold_document_missing", "fatal", scope,
                        "Golden doc_id has no structure document", law=law, article=article,
                    ))
                    case_hard_pass = False
                    coordinate_rows.append({
                        "suite": suite_name, "case_id": case_id, "ordinal": ordinal,
                        "gold": gold, "checks": checks, "hard_pass": False,
                        "version_drift": False, "issue_categories": row_issues,
                    })
                    continue

                meta = document["meta"]
                node = document["node_by_id"].get(node_id) if node_id is not None else None
                checks.update({
                    "meta_doc_id_matches": str(meta.get("doc_id") or "") == doc_id,
                    "law_name_matches": str(meta.get("name") or "") == law,
                    "revision_matches": compact_date(meta.get("revised")) == compact_date(gold.get("document_revision")),
                    "enforcement_matches": compact_date(meta.get("enforce")) == compact_date(gold.get("document_enforcement")),
                    "node_exists": node is not None,
                    "node_is_article": bool(node and node.get("family") == "kr_article"),
                    "article_surface_matches": bool(node and canonical_article(node.get("surface")) == article),
                    "graph_section_exists": f"section:{doc_id}:{node_id}" in graph_sections,
                })
                hard_check_names = (
                    "meta_doc_id_matches", "law_name_matches", "revision_matches",
                    "enforcement_matches", "node_exists", "node_is_article",
                    "article_surface_matches", "graph_section_exists",
                )
                corpus_status = str(gold.get("corpus_status") or "")
                current_candidates = current_articles.get((law, article), [])
                current_corpus_status = (
                    "present" if len(current_candidates) == 1
                    else "missing_article" if not current_candidates
                    else "ambiguous_article"
                )
                current_statuses.append(current_corpus_status)
                corpus_status_drift = current_corpus_status != corpus_status
                if corpus_status_drift:
                    issues.append(make_issue(
                        "gold_corpus_status_drift", "gold_drift", scope,
                        "Frozen corpus_status differs from the repository's current resolver contract",
                        frozen=corpus_status, current=current_corpus_status,
                        current_candidates=current_candidates,
                    ))
                expected_missing = corpus_status == "missing_article"
                if expected_missing:
                    hard_check_names = (
                        "meta_doc_id_matches", "law_name_matches", "revision_matches",
                        "enforcement_matches",
                    )
                    declared_surface_absent = not document["article_by_surface"].get(article)
                    checks["declared_missing_surface_absent"] = declared_surface_absent
                    if not declared_surface_absent:
                        issues.append(make_issue(
                            "declared_missing_article_now_present", "fatal", scope,
                            "Golden corpus_status says missing_article but the surface exists in its document",
                            gold=gold,
                        ))
                        case_hard_pass = False
                    current_alternatives = []
                    for alt_doc_id, alt_document in sorted(documents.items()):
                        alt_meta = alt_document["meta"]
                        if (alt_doc_id != doc_id and alt_meta.get("name") == law
                                and alt_meta.get("status") == "현행"
                                and alt_document["article_by_surface"].get(article)):
                            for alt_node in alt_document["article_by_surface"][article]:
                                current_alternatives.append({
                                    "doc_id": alt_doc_id,
                                    "node": alt_node.get("id"),
                                    "article": article,
                                    "title": alt_node.get("title"),
                                    "enforce": alt_meta.get("enforce"),
                                    "revised": alt_meta.get("revised"),
                                    "status": alt_meta.get("status"),
                                })
                    if current_alternatives:
                        issues.append(make_issue(
                            "declared_missing_available_in_status_current", "metadata_conflict", scope,
                            "Article absent from law_index-selected gold document exists in a same-law document marked 현행",
                            gold=gold, alternatives=current_alternatives,
                        ))
                for check_name in hard_check_names:
                    if not checks[check_name]:
                        category = f"gold_{check_name}"
                        row_issues.append(category)
                        issues.append(make_issue(
                            category, "fatal", scope,
                            "Golden coordinate failed a hard integrity check",
                            check=check_name, gold=gold,
                            meta={key: meta.get(key) for key in (
                                "doc_id", "name", "revised", "enforce", "status", "series"
                            )},
                            node=node,
                        ))
                        case_hard_pass = False

                index_row = index_by_name.get(law)
                authoritative_doc_id = str((index_row or {}).get("doc_id") or "")
                version_drift = bool(authoritative_doc_id and authoritative_doc_id != doc_id)
                case_version_drift = case_version_drift or version_drift
                alternative: dict[str, Any] | None = None
                if version_drift:
                    authoritative = documents.get(authoritative_doc_id)
                    candidate_nodes = (
                        authoritative["article_by_surface"].get(article, [])
                        if authoritative else []
                    )
                    gold_text = article_text(document["result"], node) if node else ""
                    if len(candidate_nodes) == 1 and authoritative:
                        alt_node = candidate_nodes[0]
                        alt_text = article_text(authoritative["result"], alt_node)
                        alternative = {
                            "doc_id": authoritative_doc_id,
                            "node": alt_node.get("id"),
                            "law": (authoritative.get("meta") or {}).get("name"),
                            "article": canonical_article(alt_node.get("surface")),
                            "title": alt_node.get("title"),
                            "enforce": (authoritative.get("meta") or {}).get("enforce"),
                            "revised": (authoritative.get("meta") or {}).get("revised"),
                            "status": (authoritative.get("meta") or {}).get("status"),
                            "normalized_text_equal": normalized_text(gold_text) == normalized_text(alt_text),
                            "gold_text_sha256": sha256_bytes(normalized_text(gold_text).encode("utf-8")),
                            "alternative_text_sha256": sha256_bytes(normalized_text(alt_text).encode("utf-8")),
                        }
                    issues.append(make_issue(
                        "gold_authority_version_drift", "version_drift", scope,
                        "Golden doc_id differs from law_index authority document",
                        gold_doc_id=doc_id, gold_enforce=meta.get("enforce"),
                        gold_status=meta.get("status"), authoritative_doc_id=authoritative_doc_id,
                        authoritative_enforce=(index_row or {}).get("enforce"),
                        same_article_alternative=alternative,
                    ))

                temporal_gap = bool(
                    published and compact_date(meta.get("enforce"))
                    and compact_date(meta.get("enforce")) > published
                )
                if temporal_gap:
                    issues.append(make_issue(
                        "reference_date_precedes_gold_enforcement", "temporal_provenance_review", scope,
                        "Reference source predates the golden document enforcement date",
                        reference_date=published, gold_enforce=meta.get("enforce"),
                        suite=suite_name,
                    ))

                coordinate_rows.append({
                    "suite": suite_name,
                    "case_id": case_id,
                    "ordinal": ordinal,
                    "gold": gold,
                    "meta": {key: meta.get(key) for key in (
                        "doc_id", "name", "revised", "enforce", "status", "series", "law_serial"
                    )},
                    "node": {key: node.get(key) for key in (
                        "id", "family", "surface", "title", "span", "block"
                    )} if node else None,
                    "checks": checks,
                    "hard_pass": all(checks.get(name, False) for name in hard_check_names)
                    and (not expected_missing or checks.get("declared_missing_surface_absent", False)),
                    "scorable_present": not expected_missing,
                    "current_corpus_status": current_corpus_status,
                    "corpus_status_drift": corpus_status_drift,
                    "version_drift": version_drift,
                    "authoritative_same_article": alternative,
                    "reference_date": published,
                    "reference_date_precedes_gold_enforcement": temporal_gap,
                    "issue_categories": sorted(row_issues),
                })

            current_material = (
                "complete" if current_statuses and set(current_statuses) == {"present"}
                else "missing" if "present" not in current_statuses else "partial"
            )
            frozen_material = str(case.get("material") or "")
            material_drift = bool(frozen_material and current_material != frozen_material)
            if material_drift:
                issues.append(make_issue(
                    "gold_material_drift", "gold_drift", case_scope,
                    "Frozen case material differs from current coordinate resolution",
                    frozen=frozen_material, current=current_material,
                    coordinate_statuses=current_statuses,
                ))
            case_rows.append({
                "suite": suite_name,
                "case_id": case_id,
                "expected_article_count": len(expected_articles),
                "hard_pass": case_hard_pass,
                "has_version_drift": case_version_drift,
                "frozen_material": frozen_material,
                "current_material": current_material,
                "material_drift": material_drift,
                "reference_review": reference_review,
                "coordinate_row_range": [case_coord_start, len(coordinate_rows)],
            })
    return coordinate_rows, case_rows, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="run-001")
    args = parser.parse_args()

    cm = load_json(CM_PATH)
    fsc = load_json(FSC_PATH)
    law_index = load_json(LAW_INDEX_PATH)
    combined_hash = combined_dataset_sha256((CM_PATH, FSC_PATH))
    if combined_hash != EXPECTED_COMBINED_SHA256:
        raise SystemExit(
            f"Frozen dataset hash changed: {combined_hash} != {EXPECTED_COMBINED_SHA256}"
        )

    documents, structure_issues = discover_structure()
    graph_sections, graph_summary, graph_issues = graph_audit()
    index_by_name, index_issues = index_audit(law_index, documents)
    source_summary, source_issues = source_provenance_audit(cm, fsc)
    coordinate_rows, case_rows, gold_issues = audit_gold(
        [("cm-core-51", cm), ("fsc-hard-10", fsc)],
        documents,
        index_by_name,
        graph_sections,
    )
    all_issues = (
        structure_issues + graph_issues + index_issues + source_issues + gold_issues
    )
    all_issues.sort(key=lambda item: (
        item["severity"], item["category"], item["scope"], item["message"]
    ))

    present_rows = [row for row in coordinate_rows if row.get("scorable_present", True)]
    missing_rows = [row for row in coordinate_rows if not row.get("scorable_present", True)]
    hard_pass_coordinates = sum(bool(row["hard_pass"]) for row in present_rows)
    version_drift_coordinates = sum(bool(row["version_drift"]) for row in coordinate_rows)
    corpus_status_drift_coordinates = sum(
        bool(row.get("corpus_status_drift")) for row in coordinate_rows
    )
    current_present_coordinates = sum(
        row.get("current_corpus_status") == "present" for row in coordinate_rows
    )
    temporal_review_coordinates = sum(
        bool(row["reference_date_precedes_gold_enforcement"]) for row in coordinate_rows
    )
    reference_review_cases = sum(
        bool(row["reference_review"]["review_required"]) for row in case_rows
    )
    issue_counts = Counter(issue["category"] for issue in all_issues)
    severity_counts = Counter(issue["severity"] for issue in all_issues)
    structure_counts = {
        "directories_discovered": sum(path.is_dir() for path in STRUCTURE_ROOT.iterdir()),
        "documents_parsed": len(documents),
        "nodes": sum(doc["counts"]["nodes"] for doc in documents.values()),
        "blocks": sum(doc["counts"]["blocks"] for doc in documents.values()),
        "articles": sum(doc["counts"]["articles"] for doc in documents.values()),
        "law_index_documents": len(law_index.get("docs") or []),
    }

    output = {
        "schema_version": "golden-corpus-integrity-audit-v1",
        "adr_id": "ADR-0082",
        "run_id": args.run_id,
        "audit_date": "2026-08-27",
        "deterministic": True,
        "llm_calls": 0,
        "retrieval_calls": 0,
        "frozen_inputs": {
            "cm": {"path": str(CM_PATH.relative_to(ROOT)), "sha256": file_sha256(CM_PATH)},
            "fsc": {"path": str(FSC_PATH.relative_to(ROOT)), "sha256": file_sha256(FSC_PATH)},
            "combined_dataset_sha256": combined_hash,
            "law_index": {
                "path": str(LAW_INDEX_PATH.relative_to(ROOT)),
                "sha256": file_sha256(LAW_INDEX_PATH),
            },
            "graph": {
                "path": str(GRAPH_PATH.relative_to(ROOT)),
                "sha256": file_sha256(GRAPH_PATH) if GRAPH_PATH.exists() else None,
            },
        },
        "summary": {
            "suites": 2,
            "cases": len(case_rows),
            "gold_coordinates": len(coordinate_rows),
            "scorable_present_coordinates": len(present_rows),
            "declared_missing_coordinates": len(missing_rows),
            "current_present_coordinates": current_present_coordinates,
            "corpus_status_drift_coordinates": corpus_status_drift_coordinates,
            "material_drift_cases": sum(bool(row["material_drift"]) for row in case_rows),
            "hard_pass_coordinates": hard_pass_coordinates,
            "hard_fail_coordinates": len(present_rows) - hard_pass_coordinates,
            "hard_pass_cases": sum(bool(row["hard_pass"]) for row in case_rows),
            "hard_fail_cases": sum(not row["hard_pass"] for row in case_rows),
            "version_drift_coordinates": version_drift_coordinates,
            "version_drift_cases": sum(bool(row["has_version_drift"]) for row in case_rows),
            "reference_completeness_review_cases": reference_review_cases,
            "temporal_provenance_review_coordinates": temporal_review_coordinates,
            "issues_total": len(all_issues),
            "issues_by_severity": dict(sorted(severity_counts.items())),
            "issues_by_category": dict(sorted(issue_counts.items())),
        },
        "structure_summary": structure_counts,
        "graph_summary": graph_summary,
        "source_provenance": source_summary,
        "cases": case_rows,
        "gold_coordinates": coordinate_rows,
        "issues": all_issues,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.write_bytes(encoded)
    print(json.dumps({
        "output": str(args.output),
        "sha256": sha256_bytes(encoded),
        "bytes": len(encoded),
        "summary": output["summary"],
        "structure_summary": structure_counts,
        "graph_summary": graph_summary,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
