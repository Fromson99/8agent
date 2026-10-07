"""Read-only verification of the final design artifacts, not product/LLM tests."""
from pathlib import Path
import hashlib, json, re
from jsonschema import Draft202012Validator

base=Path(__file__).resolve().parent
def read(name): return json.loads((base/name).read_text())
checks=[]
def check(name, value):
    checks.append({"name":name,"passed":bool(value)})
    if not value: raise AssertionError(name)

decisions=read("decisions.json")["decisions"]
sources=read("sources.json")["sources"]
scenarios=read("acceptance-scenarios.json")["scenarios"]
source_map={s["id"]:s for s in sources}
check("20_unique_decisions",len(decisions)==len({d["id"] for d in decisions})==20)
check("20_pending_product_scenarios",len(scenarios)==20 and all(s["status"]=="pending_product_implementation_and_validation" for s in scenarios))
check("decisions_to_scenarios", {(d["id"],d["test_id"]) for d in decisions}=={(s["decision_id"],s["id"]) for s in scenarios})
check("all_decision_sources_resolve", all(set(d["source_ids"])<=source_map.keys() for d in decisions))
check("source_snapshot_hashes", all(hashlib.sha256(Path(s["path"]).read_bytes()).hexdigest()==s["sha256"] for s in sources))
for doc in base.glob("*.md"):
    content=doc.read_text()
    check(doc.name+"_balanced_fences",len(re.findall(r"^~~~",content,re.M))%2==0)
    for target in re.findall(r"\]\(([^)]+)\)",content):
        if target.startswith(("https://","http://","#")):continue
        file=target.split("#",1)[0]
        check(doc.name+"_link_"+file,(base/file).exists())

schema=read("control.schema.json")
Draft202012Validator.check_schema(schema)
validator=Draft202012Validator(schema)
example_checks=[]
for name,expected in (("valid",True),("invalid",False)):
    for i,value in enumerate(read("control-examples.json")[name],1):
        passed=validator.is_valid(value)==expected
        example_checks.append({"name":f"{name}_{i}","passed":passed})
        assert passed
check("control_schema_shape_examples",all(e["passed"] for e in example_checks))
audit=json.loads(Path(source_map["S04"]["path"]).read_text())
check("audit_count_correction", [audit["compose"][a]["calls"] for a in ("plain-flash","audit-flash","plain-qwen","audit-qwen")]==[91,274,92,282])
profile=json.loads(Path(source_map["S05"]["path"]).read_text())
check("opposite_profile_effects",[profile["by_arm"][a]["run-001"] for a in ("loop2-flash","loop2c-flash","loop2-qwen","loop2c-qwen")]==[38,36,30,34])
diags=json.loads(Path(source_map["S08"]["path"]).read_text())["results"]
check("presentation_count_deltas",[diags[a]["created_card_case_pairs"]-diags[a]["payload_card_case_pairs"] for a in ("loop3-flash","loop3-qwen")]==[57,54])
check("hypothetical_arithmetic",abs(0.5/(176/51)*100-14.5)<0.05 and abs(0.7/(176/51)*100-20.3)<0.05)
review=(base/"SELF_REVIEW.md").read_text()
check("reviewed_document_hash",hashlib.sha256((base/"FINAL_DESIGN.md").read_bytes()).hexdigest() in review)
check("reviewed_matrix_hash",hashlib.sha256((base/"DESIGN_RATIONALE.md").read_bytes()).hexdigest() in review)
result={"scope":"Document links, source snapshots, traceability, arithmetic, and synthetic control JSON shape only. No product reducer/coordinator, serving integration, legal quality, or GENOS validation.",
"document_checks_passed":len(checks),"control_shape_examples_passed":len(example_checks),"planned_product_scenarios":len(scenarios),"product_scenarios_executed":0,"failed":0,"hypothetical_call_increase_percent":[0.5/(176/51)*100,0.7/(176/51)*100]}
print(json.dumps(result,ensure_ascii=False,indent=2))

