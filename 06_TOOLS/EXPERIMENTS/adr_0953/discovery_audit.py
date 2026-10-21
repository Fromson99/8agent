"""Offline source-coordinate and internal-to-external task audit; no product writes."""
from pathlib import Path
import json
import sqlite3

R = Path(__file__).resolve().parents[3]
A = R / "04_EXPERIMENTS/ADR/ADR-0953-risk-photo-authorized-live"
O = A / "artifacts/run-001"
load = lambda p: json.loads(p.read_text())
G = R / load(A / "artifacts/design/baseline.json")["manifest"]["data_path"]


def connect(p):
    db = sqlite3.connect("file:" + str(p) + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


source = connect(G / "store.sqlite")
targets = {
    "liquidity": [
        ("7a3907e193ec6c14", "body:제6-4조제1항"),
        ("7a3907e193ec6c14", "body:제6-4조제2항"),
        ("c9b5b42627710637", "body:제3-24조의4제2항"),
    ],
    "leverage": [
        ("7a3907e193ec6c14", "body:제2-1조제1항제3호"),
        ("7a3907e193ec6c14", "body:제1-4조제1항제3호"),
        ("c9b5b42627710637", "body:제3-6조"),
        ("c9b5b42627710637", "body:제3-24조의4"),
        ("c9b5b42627710637", "body:제3-26조제7항"),
    ],
}
out = {"scope": "Post-run diagnostic. User-specified coordinates are not approved legal gold. No prompt injection, no new model calls.", "cases": {}}
for case, requested in targets.items():
    P = O / "live" / case
    audit = load(P / "audit.json")
    body = load(P / "response.json")["body"]
    all_spans, read_ids, parent_spans = [], set(), {}
    task_rows, read_statuses, tool_counts = [], [], []
    for journal in audit["journals"]:
        db = connect(R / journal["path"])
        side = journal["side"]
        statuses = db.execute("select tool,status,count(*) as n from observation group by tool,status").fetchall()
        tool_counts += [{"side": side, **dict(row)} for row in statuses]
        read_statuses += [{"side": side, **dict(row)} for row in statuses if row["tool"] in ("read", "read_node")]
        for row in db.execute("select status,result_json from observation where tool in ('read','read_node')"):
            if row["status"] in ("OK", "TRUNCATED"):
                read_ids.update(json.loads(row["result_json"]).get("evidence_ids", []))
        for row in db.execute("select e.evidence_id,e.document_id,s.block_id,s.start_cp,s.end_cp,s.text from evidence_unit e join evidence_span s on e.evidence_id=s.evidence_id"):
            value = dict(row)
            value["side"] = side
            if side == "parent":
                parent_spans.setdefault(value["evidence_id"], []).append(value)
            else:
                all_spans.append(value)
        if side == "parent":
            for row in db.execute("select call_id,input_json from workflow_call where kind='rag' order by rowid"):
                v = json.loads(row["input_json"])
                task = v["args"]["task"]
                task_rows.append({
                    "call_id": row["call_id"], "side": v["side"],
                    "question": v["args"]["question"], "task": task,
                    "has_previous_same_side_result": v["args"].get("previous") is not None,
                    "input_receipt": journal["path"] + "#workflow_call/" + row["call_id"],
                })
        db.close()
    read_spans = [s for s in all_spans if s["evidence_id"] in read_ids]
    returned_ids = set()
    for v in body.get("rag_results", {}).values():
        returned_ids.update(v.get("evidence_ids", []))
    returned_spans = [s for eid in returned_ids for s in parent_spans.get(eid, [])]
    final_spans = [s for eid in body.get("evidence_refs", []) for s in parent_spans.get(eid, [])]
    # Exact field citation text is narrower than an evidence unit's whole read scope.
    exact_citations = []
    for item in body.get("comparison_items", {}).get("items", []):
        for side in ("internal", "external"):
            for c in item.get(side, {}).get("citations", []):
                for s in parent_spans.get(c.get("evidence"), []):
                    quote = c.get("quote", "")
                    if quote and quote in s["text"]:
                        exact_citations.append({**s, "quote": quote})
    rows = []
    for doc, coord in requested:
        units = source.execute("select unit_id,json from source_unit where document_id=? and json_extract(json,'$.coordinate_key') like ?", (doc, coord + "%")).fetchall()
        units = [r for r in units if json.loads(r["json"]).get("coordinate_key") == coord or json.loads(r["json"]).get("coordinate_key", "").startswith(coord + "제")]
        unit_ids = {r["unit_id"] for r in units}
        blocks = {r["block_id"]: r["text"] for r in source.execute("select block_id,unit_id,text from source_block where document_id=?", (doc,)) if r["unit_id"] in unit_ids}
        stages = {}
        for name, spans in (("read", read_spans), ("returned", returned_spans), ("final_evidence", final_spans), ("field_literal_citation", exact_citations)):
            hits = [s for s in spans if s["document_id"] == doc and s["block_id"] in blocks]
            stages[name] = {"blocks": sorted({s["block_id"] for s in hits}, key=int), "evidence_ids": sorted({s["evidence_id"] for s in hits})}
        rows.append({"document_id": doc, "coordinate": coord, "exists_in_frozen_data": bool(units), "target_blocks": sorted(blocks, key=int), "stages": stages})
    basis_db_path = P / "runtime/basis-links/authority.sqlite"
    basis_db = connect(basis_db_path)
    heads = [dict(r) for r in basis_db.execute("select * from basis_head")]
    proposals = [{"link_id": r["link"]["link_id"], "kind": r["link"]["kind"], "status": r["link"]["status"],
                  "internal": [{"document_id": e["document_id"], "unit_id": e["unit_id"]} for e in r["link"]["internal"]],
                  "external": [{"document_id": e["document_id"], "unit_id": e["unit_id"]} for e in r["link"]["external"]]}
                 for r in body.get("basis_links", {}).get("items", [])]
    basis_db.close()
    persistence = {"database": str(basis_db_path.relative_to(R)), "heads": heads, "response_proposals": proposals,
                   "all_response_ids_in_database": all(p["link_id"] in {r["link_id"] for r in heads} for p in proposals),
                   "production_oracle_written": False, "scope": "Isolated per-case local test state; no human approvals."}
    out["cases"][case] = {"target_coverage": rows, "rag_task_inputs": task_rows, "read_statuses": read_statuses, "tool_counts": tool_counts,
                         "mapping_persistence": persistence}
(O / "discovery-audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({case: [{"coordinate": r["coordinate"], "read_blocks": len(r["stages"]["read"]["blocks"]), "final_blocks": len(r["stages"]["final_evidence"]["blocks"]), "literal_cited_blocks": len(r["stages"]["field_literal_citation"]["blocks"]), "target_blocks": len(r["target_blocks"])} for r in value["target_coverage"]] for case, value in out["cases"].items()}, ensure_ascii=False, indent=2))
