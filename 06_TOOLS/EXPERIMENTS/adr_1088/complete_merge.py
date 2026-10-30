from pathlib import Path
import json,hashlib,shutil,ast,sys
R=Path(__file__).resolve().parents[3];D=R/'06_TOOLS/EXPERIMENTS/adr_1088';C=R/'02_BACKEND/lawrag/research/candidates/adr_1088/a1-combined-r1';S=C/'snapshot';P=S/'02_BACKEND/semantic_runtime/legal_agent'
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
# Copy the completed common parent's contract tests without changing them.
common=R/'02_BACKEND/lawrag/research/candidates/adr_1086/compact-r1/revisions/rev-004/snapshot'
for n in ('test_compact_model_input.py','test_compact_wire_binding.py','test_journal_evidence_batch.py'):
 name='05_TESTS/CONTRACTS/'+n;shutil.copyfile(R/name,S/name);ac.register_file(C,name,upstream_state="present")
for p in P.glob('*.py'):ast.parse(p.read_text())
A=R/'04_EXPERIMENTS/ADR/ADR-1088-ontology-a1-compact-integration';m=json.loads((A/'실험/manifest.json').read_text())
m['integration']['conflicts']=[{'area':'common/ontology shared call sites','resolution':'Keep ontology task-local/action codec/review ownership; page canonical schema independently binds current targets. Each page has distinct transition and correction identity. READ_CHOICE_SELECTED identifies actual transition; menu key separately retained.'},{'area':'model input proof','resolution':'Project common minimal input first, then legacy optional projection. Independently rebuild both from canonical stored view; retain both receipts.'},{'area':'configuration/profile','resolution':'Preserve every ontology flag; add only minimal_input and page_size20. Original legacy fixtures explicitly use their old projection, combined fixtures enable both.'}]
m['integration']['rollback_plan']='Retain exact1087and1086 parents; candidate only. Stop on source/selection/state mismatch; no MAIN or GENOS pointer mutation.'
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(R/'06_TOOLS/EXPERIMENTS/adr_1087/test_ontology_optimization.py',D/'test_ontology_optimization.py')
p=D/'test_ontology_optimization.py';s=p.read_text().replace("    repo=S(db=db); sql=[]; db.set_trace_callback(sql.append)\n    rows=list(io.delivery_events", "    db.commit()\n    repo=S(db=db); sql=[]; db.set_trace_callback(sql.append)\n    rows=list(io.delivery_events");p.write_text(s)
print('Product syntax and selective conflict resolutions ready; tests not run.')
