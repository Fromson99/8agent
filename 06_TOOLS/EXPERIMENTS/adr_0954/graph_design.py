"""Prospective, user-directed graph input; no answer or model-generated conclusion."""
import json
import sqlite3

criteria = {
    "hypothesis": "Finding internal originals first and resolving their manually seeded DB edges supplies the intended external originals to the unchanged comparison workflow.",
    "primary_metric": "Seeded edges actually selected from read internal spans, external originals read and handed to parent, final comparison citation and meaning reviewed separately.",
    "selection": "Same two questions and four source documents as ADR0953, one linked request each, sequential liquidity then leverage. Archived ADR0953/live is a historical control; no paired causal speed/quality claim.",
    "controls": "MAIN92/workflow1.19.4 product Python, prompts, schema, search settings, model and source generation unchanged. Only isolated authorization metadata/pins and four manually activated basis records differ.",
    "success": [
        "Source-coordinate graph is persisted through existing proposal/review APIs and resolves from internal read spans into native external read_node.",
        "Liquidity reads and cites 금융투자업규정 제3-24조의4 제2항, retains internal 제6-4조 and distinguishes formula from minimum maintenance obligations.",
        "Leverage retains internal 제2-1조 제1항 제3호 and external 제3-6조 definition, 제3-24조의4 제1항 and 제3-26조 제7항; maintenance and reporting conditions are distinguished.",
        "Final response preserves company applicability, partial internal document and unknown effective date; does not claim a whole-document absence.",
        "Exact source hashes, ACL, scoped authorization, duplicate/status responses, fixed budgets and unchanged MAIN pass."
    ],
    "failure": [
        "Source/hash/ACL/state corruption, fabricated original or silently dropped failure.",
        "Graph accepted in DB but absent from external task/read/parent delivery.",
        "Intended originals acquired but major governing-rule/applicability errors remain; record as semantic failure without repeated model repair.",
        "Unrecorded physical calls, automatic adaptive replay or exceeded budgets."
    ],
    "limits": {"physical_calls_per_question": 40, "wall_seconds_per_question": 1800, "physical_call_seconds": 180,
               "worker_rss_gib": 6, "address_space_gib": 8, "minimum_available_gib": 4, "minimum_disk_gib": 10, "sequential": True},
    "retry_contract": {"owner": "Existing ModelGateway only", "max_transport_retries": 1, "client_retries": 0, "sequence_retries": 0,
                      "unknown_outcome": "Preserve and stop; no blind request replay",
                      "seed_failure": "Persist failed API receipt; no model call; no bypass of source/review/ACL checks."},
    "legal_accuracy_certified": False, "full_MAIN_corpus": False, "manual_graph_visible_to_product": True,
    "limitations": [
        "Known target source coordinates are intentionally supplied as product graph inputs at user request; this measures downstream comparison, not automatic edge discovery.",
        "APPROVED is the isolated runtime's activation state only, not legal approval or a production authority change.",
        "Internal source is partial, effective date unknown; external sources are the previously frozen edition.",
        "No whole-document comparison or Oracle/GENOS deployment; historical single-run control only.",
        "No answer gold, conclusion text or final assessment is seeded. No offline evaluator model."
    ]
}


def graph(generation):
    db = sqlite3.connect("file:" + str(generation / "store.sqlite") + "?mode=ro", uri=True)
    internal, regulation, annex = "7a3907e193ec6c14", "c9b5b42627710637", "bfc333a2a8c71fea"

    def coordinate(did, coord):
        rows = db.execute("select unit_id from source_unit where document_id=? and json_extract(json,'$.coordinate_key')=?", (did, coord)).fetchall()
        assert len(rows) == 1, (did, coord)
        return {"document_id": did, "unit_id": rows[0][0]}

    def node(did, uid):
        assert db.execute("select 1 from source_unit where document_id=? and unit_id=?", (did, str(uid))).fetchone()
        return {"document_id": did, "unit_id": str(uid)}

    def link(ident, source, targets, explicit):
        return {"id": ident, "internal": [source], "external": targets, "kind": "BASIS",
                "reason": "사용자 요청에 따른 일부 조항 대사 시험용 수동 연결. 연결된 양쪽 원문을 읽어 적용 대상과 내용의 대응 여부를 판단한다. 법률적 일치·충돌 결론은 주입하지 않는다.",
                "provenance": {"type": "USER_SELECTION", "experiment_id": "ADR-0954-experiment-v1",
                               "purpose": "forced_graph_downstream_comparison", "test_only": True,
                               "explicit_reference_visible_in_internal": explicit,
                               "legal_relation_certified": False}}

    links = [
        link("liquidity-maintenance", coordinate(internal, "body:제6-4조제1항"),
             [coordinate(regulation, "body:제3-24조의4제2항")], False),
        link("liquidity-explicit-annex", coordinate(internal, "body:제6-4조제2항"),
             [node(annex, u) for u in (25, 26, 56)], True),
        link("leverage-explicit-definition", coordinate(internal, "body:제1-4조제1항제3호"),
             [coordinate(regulation, "body:제3-6조제4호")], True),
        link("leverage-maintenance-reporting", coordinate(internal, "body:제2-1조제1항제3호"),
             [coordinate(regulation, c) for c in ("body:제3-6조제4호", "body:제3-24조의4제1항", "body:제3-26조제7항")], False),
    ]
    db.close()
    return {"schema": "forced-source-graph-test-v1", "test_only": True, "same_graph_for_both_questions": True,
            "legal_answer_gold": False, "activation_authorized_by_user": True,
            "relationship_records": 4, "directed_endpoint_edges": 8, "links": links}
