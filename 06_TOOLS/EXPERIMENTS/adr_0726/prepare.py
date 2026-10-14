from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0726-lossless-navigation-input';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
ptr=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(ptr);manifest=read(R/pointer['manifest_path']);assert pointer['generation']==51
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(ptr),'manifest':manifest})
criteria={'scope':'MAIN51 external wire schema factorization; source-local evidence text/metadata projection; typed structure target contract; question-driven bounded reading guidance; measure existing latency without unsafe cache changes.', 'required':['Schema reference expansion equals input schema exactly; all local validators remain unchanged except rejecting already-invalid typed global lookup at generation time','Every delivered source text and citation option text/id remains exact; source identity collisions never merge','All existing contracts run on frozen code; no new regression versus selected MAIN51','Fresh public qualification required before working code or MAIN changes'], 'probe':'Archived H02 inputs for deterministic schema/projection size ablation; no new model calls, no legal accuracy claim', 'qualification':'Next ADR, unchanged code, three fresh public primary roots; original support and no paired supported regression, aggregate input reduction >=10%, calls <=baseline+2 and time <=baseline*1.3; detailed semantics recorded separately. No adaptive rerun.', 'authorization':'User authorized prior local MAIN integration and external public cases; now instructed proceed with optimization.'}
put(D/'criteria.json',criteria);put(D/'dataset.json',{'cases':['Archived ADR0725 H02 physical payloads, product response untouched','Synthetic source and tool-menu boundaries'],'product_gold':False})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Exact wire schema equivalence and preserved original evidence with fewer bytes',success_criteria=criteria['required'],failure_criteria='Any source/state/schema boundary regression',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for x in m['design']['arms']:x.update(changes='Selected MAIN51' if x['id']=='baseline' else criteria['scope'],controls='Same immutable sources and raw archived input; zero model calls')
m['runs'][0].update(arm_ids=['compact'],selection_rule='Deterministic archived input ablation and all contracts; no new model results',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='Recorded H02 plus synthetic boundaries',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['retrieval_accounting'].update(changed=False,not_applicable_reason='Recorded payload representation only; no retrieval re-execution or candidate selection measurement');m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason'];put(A/'실험/manifest.json',m)
parent=read(R/'02_BACKEND/lawrag/research/candidates/adr_0725/integrated/candidate.json')
paths=set(manifest['files'])|{x['target_path'] for x in parent['files']}
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','compact','--experiment-id',m['experiment_id'],'--arm-id','compact','--run-id','run-001']
for p in sorted(paths):
 assert (R/p).is_file(),p
 if p in manifest['files']:assert sha(R/p)==manifest['files'][p],p
 cmd+=['--source',p]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Frozen design; isolated',len(paths),'files from selected MAIN51 and tests')
