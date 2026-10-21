from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0905-closed-reference-continuity'; D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
c={'hypothesis':'Retain validated closed reference judgments in subsequent context and apply the same reuse guard when returning to a reference frame.',
'success':['SKIP and its actual reason/applicability survive overview and model wire; no false pending solely from closed references','Returning to identical SKIP or completed FOLLOW requires zero further reference model calls, including checkpoint resume','Fresh witnesses are authorized and revalidated before reuse; changed witness requires fresh judgment; stale generation/scope/question fails binding','DEFER and incomplete FOLLOW remain unresolved; conflicting or malformed decisions are never promoted to completed legal judgments','Originals, budgets, repair, failure history and actual API dispatch retain existing contracts; immutable archived frames retained'],
'failure':['Source, ACL, state, hash, budget or recovery regression','Code drift or resource guard stop'],
'evaluation':'Finite synthetic software boundary checks with scripted transport; ADR0904 known diagnosis is not a legal holdout or timing comparison. No external model calls.',
'recovery':{'owner':'Existing reference DecisionJournal and host navigation validator','max_added_model_calls':0,'stale_replay':'Host ContractError with existing failure diagnostics; no model retry','invalid_cached_decision':'Never close; ordinary bounded current-menu decision path','unfinished':'Preserve DEFER and pending reads; no forced semantic closure','resume':'Preserve decision receipts, accepted operations and checkpoint budgets'},
'limits':{'workers':1,'rss_gib':2,'as_gib':3,'min_available_gib':4,'min_disk_gib':10},'legal_holdout':False,'genos_execution':False}
put(D/'criteria.json',c)
f=read(R/'04_EXPERIMENTS/ADR/ADR-0903-read-input-connected-contract/artifacts/design/freeze.json');cm=read(R/f['candidate']['manifest_path']);names=[x['target_path'] for x in cm['files']]
before={n:sha(R/n) for n in names};assert all(sha(R/f['code_root']/n)==h for n,h in before.items());put(D/'working-before.json',before)
active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':read(R/active['manifest_path']),'parent_code_root':f['code_root'],'working_equals_parent':True})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Finite closed-reference continuity contracts',success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'retained','role':'candidate','derived_from':['ADR-0903-experiment-v1/qualified'],'changes':c['hypothesis'],'controls':'Same code/data contracts, models, outputs and persistent budgets; only closure propagation and replay reuse change.'}]
m['runs'][0].update(arm_ids=['retained'],selection_rule=c['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='closed-reference-continuity-contracts',version='20261019-r1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));m['llm_policy']['llm_calls']=[]
why='Finite synthetic software contracts; no model, retrieval or legal quality comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','retained','--experiment-id',m['experiment_id'],'--arm-id','retained','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL);print('Criteria and 712-file isolated snapshot prepared; data shared, no loading.')
