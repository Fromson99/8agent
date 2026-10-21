"""Audit graph input -> selected endpoints -> native reads -> parent -> citation."""
from pathlib import Path
import json
import sqlite3

R = Path(__file__).resolve().parents[3]
A = R / "04_EXPERIMENTS/ADR/ADR-0954-risk-photo-forced-graph"
O = A / "artifacts/run-001"
load = lambda p: json.loads(p.read_text())
G = R / load(A / "artifacts/design/baseline.json")["manifest"]["data_path"]
source = sqlite3.connect("file:" + str(G / "store.sqlite") + "?mode=ro", uri=True)
out = {"automatic_discovery_test": False, "source_edges_intentionally_product_visible": True,
       "baseline": "ADR-0953-experiment-v1/live (archived single-run observation)", "cases": {}}
for case in ("liquidity", "leverage"):
    P = O / "linked" / case
    a = load(P / "audit.json")
    response = load(P / "response.json")["body"]
    parent = next(j for j in a["journals"] if j["side"] == "parent")
    db = sqlite3.connect("file:" + str(R / parent["path"]) + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    tasks = []
    for row in db.execute("select call_id,input_json from workflow_call where kind='rag' order by rowid"):
        value = json.loads(row["input_json"])
        if value["side"] == "external":
            task = value["args"]["task"]
            tasks.append({"call_id": row["call_id"], "snapshot": task.get("basis_snapshot"), "targets": task.get("basis_targets", [])})
    evidence = {r["evidence_id"]: dict(r) for r in db.execute("select * from evidence_unit")}
    spans = {e: [dict(r) for r in db.execute("select * from evidence_span where evidence_id=?", (e,))] for e in evidence}
    returned = set(response.get("rag_results", {}).get("external", {}).get("evidence_ids", []))
    cited = set(response.get("evidence_refs", []))
    literal = [c for item in response.get("comparison_items", {}).get("items", [])
               for c in item.get("external", {}).get("citations", [])]
    child_read_spans, read_receipts = [], []
    for journal in a["journals"]:
        if journal["side"] != "external":
            continue
        child = sqlite3.connect("file:" + str(R / journal["path"]) + "?mode=ro", uri=True)
        child.row_factory = sqlite3.Row
        for row in child.execute("select * from observation where tool='read_node'"):
            r = dict(row)
            read_receipts.append({k: v for k, v in r.items() if k not in ("result_json", "input_json")})
        child_read_spans += [dict(r) for r in child.execute("select e.document_id,s.block_id,s.start_cp,s.end_cp,s.text from evidence_unit e join evidence_span s on e.evidence_id=s.evidence_id")]
        child.close()
    targets = tasks[0]["targets"]
    rows = []
    for target in targets:
        end = target["endpoint"]
        did = end["document_id"]
        chosen = end["spans"]

        def covers(target_span, observed):
            return any(s["block_id"] == target_span["block_id"] and s["start_cp"] <= target_span["start_cp"]
                       and s["end_cp"] >= target_span["end_cp"] for s in observed)

        read = [s for s in child_read_spans if s["document_id"] == did]
        ret = [s for eid in returned if evidence[eid]["document_id"] == did for s in spans[eid]]
        final = [s for eid in cited if evidence[eid]["document_id"] == did for s in spans[eid]]
        quote_hits = []
        for c in literal:
            eid = c["evidence"]
            if evidence[eid]["document_id"] != did:
                continue
            for s in spans[eid]:
                if c["quote"] in s["text"] and any(covers(x, [s]) for x in chosen):
                    quote_hits.append(c)
                    break
        rows.append({"document_id": did, "unit_id": end["unit_id"], "title": end["title"],
                     "linked_span_count": len(chosen), "read_all_linked_spans": all(covers(s, read) for s in chosen),
                     "parent_received_all_linked_spans": all(covers(s, ret) for s in chosen),
                     "final_evidence_contains_linked_span": any(covers(s, final) for s in chosen),
                     "literal_citation_count": len(quote_hits)})
    old = load(R / f"04_EXPERIMENTS/ADR/ADR-0953-risk-photo-authorized-live/artifacts/run-001/live/{case}/result.json")
    current = load(P / "result.json")
    out["cases"][case] = {"task_count": len(tasks), "selected_links": len(tasks[0]["snapshot"]["items"]),
                          "selected_endpoints": len(targets), "read_node_receipts": read_receipts,
                          "edges": rows, "raw_tasks": tasks,
                          "historical_control": {k: old[k] for k in ("status", "model_calls", "elapsed_seconds")},
                          "linked_result": {k: current[k] for k in ("status", "model_calls", "elapsed_seconds")}}
    db.close()
(O / "graph-trace.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: {"selected_links": v["selected_links"], "endpoints": v["selected_endpoints"],
                     "native_reads": len(v["read_node_receipts"]),
                     "all_read": all(e["read_all_linked_spans"] for e in v["edges"]),
                     "all_parent_received": all(e["parent_received_all_linked_spans"] for e in v["edges"]),
                     "cited_endpoints": sum(e["literal_citation_count"] > 0 for e in v["edges"])}
                  for k, v in out["cases"].items()}, ensure_ascii=False, indent=2))
