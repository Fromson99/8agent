from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0857-host-assembly-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'02_BACKEND/lawrag/research/candidates/adr_0856/assembled';C=R/'02_BACKEND/lawrag/research/candidates/adr_0857/qualified'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'hypothesis':'The exact completed0856 product code satisfies the prospective complete software boundary census and current full pipeline consumers.', 'success':['All declared finite contract states pass','Recorded missing queries reconstruct and cross-action target remains rejected','All selected static schema nodes are valid before/after projection','Basis/workflow/API/ACL/source/hash/resume/budget consumers retained','Same code/pins/data validated before and after selective working integration and MAIN promotion'], 'failure':['Any new contract or consumer regression','Unexpected third-party bytes or main/data drift','Semantic inference or permission/state/hash bypass'], 'matrix':{'inactive_fields':['omitted current generation','well-typed legacy supplied','illegal target'], 'actions':'all18 navigation actions with valid/missing reason/missing query/wrong target', 'adapters':['gateway','bounded source','AD','GENOS build','VLM','workflow recovery','numbered refs','legacy partial consumers'], 'fulltext':['search/read leaf scope','paging continuation','hash and ACL','adaptive read']}, 'evaluation':'Prospective finite software state census, not a legal holdout. Prior captured failures are separately identified regressions. Exact product bytes from completed probe; only synthetic test fixture corrected.', 'model_calls':0,'recovery':'Existing stage/gateway single repair owners unchanged; codec issues no calls; same deadlines and persistent counters; no inference or raw overwrite.', 'live_followup':'Separate pre-frozen public fulltext actual-model audit before MAIN apply; GENOS unavailable.'}
put(D/'criteria.json',criteria)
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0856-host-assembled-output-contract/artifacts/design/freeze.json');S=R/parent['code_root'];cm=read(P/'candidate.json')
baseline=read(R/'04_EXPERIMENTS/ADR/ADR-0856-host-assembled-output-contract/artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256']
put(D/'baseline.json',baseline);put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']});put(D/'data-binding.json',{'path':baseline['release']['data_path'],'manifest_sha256':baseline['release']['data_manifest_sha256']})
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id','ADR-0857-experiment-v1','--arm-id','qualified','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in cm['files']:shutil.copyfile(S/x['target_path'],C/'snapshot'/x['target_path'])
put(D/'parent-bytes.json',{x['target_path']:sha(S/x['target_path']) for x in cm['files']})
for name in ('run_tests.py','consumer.py','preview.py','test_contracts.py','test_minimal_output.py','seal.py'):
 t=(T.parent/'adr_0856'/name).read_text().replace('adr_0856/assembled','adr_0857/qualified').replace('ADR-0856-host-assembled-output-contract','ADR-0857-host-assembly-qualification').replace('ADR-0856-experiment-v1','ADR-0857-experiment-v1').replace("'candidate_id':'assembled'","'candidate_id':'qualified'").replace("'arm_id':'assembled'","'arm_id':'qualified'")
 if name=='test_contracts.py':t=t.replace("expected=True\n", "expected=True\n    if kind=='PENDING':raw.pop('targets');raw.pop('exploration')\n")
 if name=='seal.py':
  t=t.replace("tests=[str(T.relative_to(R)/'test_contracts.py')]+", "tests=[str(T.relative_to(R)/'test_contracts.py'),str(T.relative_to(R)/'test_catalogue.py'),'05_TESTS/CONTRACTS/test_pipeline_unit_fulltext.py','05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py','05_TESTS/CONTRACTS/test_fulltext_location_metadata.py','05_TESTS/CONTRACTS/test_law_navigation_state_contract_adr0661.py','05_TESTS/CONTRACTS/test_genos_output_unlimited.py','05_TESTS/CONTRACTS/test_investigation_budget_settings.py']+")
  t=t.replace('defect reproduction and finite software regression, in-sample probe','prospective finite technical contract census plus separately retained regressions; no legal quality claim')
 (T/name).write_text(t)
for name in ('run_validation.py',):
 (T/name).write_text((T.parent/'adr_0853'/name).read_text().replace('ADR-0853-basis-wire-integration','ADR-0857-host-assembly-qualification'))
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Finite software contract and consumer integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='host-assembly-finite-contract-census',version='20261018-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
for arm in m['design']['arms']:arm.update(changes='Completed0856 exact product bytes' if arm['id']=='qualified' else 'Completed0856 probe record',controls=['same data/model/pins','no real model calls','same error and repair owners'])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
why='Finite software contracts; no model judgment/retrieval quality comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
print('Qualification criteria and identical product candidate ready')
