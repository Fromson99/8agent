from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0908-reference-context-continuity'; D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
c={'hypothesis':'Preserve bounded completed reference opinions across focus changes and name actual FOLLOW anchor sources in the compact tool input.',
'success':['Prior closed decision, original reason and source identities remain on next model wire after focus changes','History contains only valid bound completed choices; foreign scope/generation, failed/deferred/conflicting/incomplete decisions do not become closed','Historical opinions never authorize current tools or replace fresh reference validation; full reason entries are bounded with explicit omissions','FOLLOW option explicitly presents actual anchor document and article; return target contexts are retained','Existing closure/replay/source/ACL/hash/budget/recovery and actual API checks pass with the same code and pins'],
'failure':['Source, ACL, state, hash, budget or recovery regression','Unbounded history or source text duplication','Resource stop or code drift'],
'evaluation':'Finite software input/continuity boundaries with scripted transport. Known ADR0907 observation is diagnosis, not a legal holdout or performance result.',
'recovery':{'owner':'Existing reference DecisionJournal and navigation validator','added_model_calls':0,'history':'Read-only prior opinions; invalid, conflicting or foreign entries are omitted, never auto-adopted','bounds':'16 unique closed groups / 8000 serialized characters, complete entries only, explicit omitted count'},
'limits':{'workers':1,'rss_gib':2,'as_gib':3,'min_available_gib':4,'min_disk_gib':10},'legal_holdout':False,'genos_execution':False}
put(D/'criteria.json',c)
f=read(R/'04_EXPERIMENTS/ADR/ADR-0906-closed-reference-qualified/artifacts/design/freeze.json');cm=read(R/f['candidate']['manifest_path']);names=[x['target_path'] for x in cm['files']]
before={n:sha(R/n) for n in names};assert all(sha(R/f['code_root']/n)==h for n,h in before.items());put(D/'working-before.json',before)
active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':read(R/active['manifest_path']),'parent_code_root':f['code_root'],'working_equals_parent':True})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Finite closed-reference continuity contracts',success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'retained','role':'candidate','derived_from':['ADR-0906-experiment-v1/qualified'],'changes':c['hypothesis'],'controls':'Same code/data contracts, models, outputs and persistent budgets; only closure propagation and replay reuse change.'}]
m['runs'][0].update(arm_ids=['retained'],selection_rule=c['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='closed-reference-continuity-contracts',version='20261019-r1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));m['llm_policy']['llm_calls']=[]
why='Finite synthetic software contracts; no model, retrieval or legal quality comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','retained','--experiment-id',m['experiment_id'],'--arm-id','retained','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL);print('Criteria and 712-file isolated snapshot prepared; data shared, no loading.')
