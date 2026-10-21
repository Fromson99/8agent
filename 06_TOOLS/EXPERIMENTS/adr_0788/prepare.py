from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0788-navigation-finish-delivery-recovery';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'scope':'FINISH requires post-decision adopted originals; precise bounded correction; confirmed source delivery survives invalid output without adoption.',
 'matrix':{'versions':['v2','v5','v6','v7','v8'],'prior_adoption':[False,True],'statuses':['OMIT','ADOPT','KEEP','DEFER','EXCLUDE'],'issue_scope':['same','other'],'expected_cases':100},
 'required':['Every prospectively enumerated state transition agrees with independent expected adoption and execution','Every required regression passes without skip/exemption','Normal response plus pinned model/view proves input delivery; timeout, stale, filter, length and mismatched identity cannot fabricate it','Delivery never becomes adoption; explicit accepted DEFER/EXCLUDE remains excluded','Correction at most once with preserved errors/deadline/budget; repeated request makes no extra call','Same frozen code used by real API tests and promoted local service; unrelated working changes preserved'],
 'failure':'Any integrity, finite contract or regression failure blocks promotion. Semantic model mistakes are separately recorded; no retrospective changes to criteria.',
 'limitations':['Synthetic technical exhaustive state domain, not unseen legal-question holdout','GENOS unavailable; exact field question/inputs absent','Model response does not certify reading comprehension or legal accuracy','JSON schema covers structure; cross-field and state-dependent completion still requires runtime validation'],
 'live_check':{'source':'Invented synthetic approval regulation only; no internal data','scenarios':['unadopted_insufficient','adopted_insufficient'],'arms':['baseline','recovery'],'max_calls':4,'model':'qwen/qwen3.8-27b','provider':'Parasail','precision':'fp8','reasoning_effort':'none','role':'product','promotional_role':'supplemental; quality observations not statistical efficacy claim'}}
put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(p);assert active['generation']==66
base=read(R/active['manifest_path']);put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(p),'manifest':base})
targets=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('law_navigation','evidence_inventory','gateway','model_contract','bounded_source_session','domain')]
targets.append('02_BACKEND/semantic_runtime/provider.py')
files=set(base['files']);put(D/'working-before.json',{'files':{n:sha(R/n) for n in files},'target_files':targets})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='100 finite adoption state contracts plus durable delivery and API regressions',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Synthetic finite completion/delivery state contracts',version='finish-delivery-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':4}]
m['runs'][0].update(selection_rule='Full predefined finite state cross product and required regression set; two synthetic model cases paired once',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Completion/delivery protocol; search policy and corpus unchanged.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No retrieval quality comparison.')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN66' if arm['id']=='baseline' else criteria['scope'],controls='Same data/search/profile/output limits; existing provider-managed cap compatibility retained in adapter dependency')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','recovery','--experiment-id',m['experiment_id'],'--arm-id','recovery','--run-id','run-001']
for n in sorted(files):cmd+=['--source',n]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0788/recovery/snapshot'
for n in files-set(targets):shutil.copy2(R/base['code_root']/n,C/n)
put(D/'initial-rebase.json',{'base_code_root':base['code_root'],'preserved_working_targets':targets,'other_files':'exact selected MAIN66 bytes; unrelated working development excluded'})
print('Prepared isolated candidate',C)
