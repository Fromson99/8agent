"""Freeze scope before editing; snapshot the exact selected MAIN inventory."""
import hashlib,json,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing'
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');b=read(R/p['manifest_path'])
drift={f:{'active':h,'working':sha(R/f)} for f,h in b['files'].items() if sha(R/f)!=h}
plan={'scope':'Remove application HMAC issuance/verification and user_wiki production/consumption; preserve session state, current shortcut DB, legal_wiki, platform API authentication and AD management gate.',
      'baseline':p,'data_generation':b['data_path'],
      'acceptance':['Unsigned workflow/native/session API requests work without a signing environment key',
                    'Input validation, explicit team/document selection and session ownership remain enforced',
                    'Correction and confirmation preserve session state; different sessions do not automatically inherit personal question history',
                    'Shortcut capture and legal_wiki compile/rebuild retain their shared repository',
                    'No user_wiki model context, query or newly generated projection; stored history remains intact',
                    'Completion, source citation, native JSON/SSE, AD gates and no-socket regressions introduce no new failures',
                    'Evaluated candidate, selected release and actual service entry match; changed runtime files match working code and unrelated pending work is preserved'],
      'dataset':'New synthetic contract cases plus maintained regression contracts; no legal quality, performance or external-model experiment',
      'model_calls':0,'quality_certified':False,'frozen_before_implementation':True}
if (D/'criteria.json').exists():assert read(D/'criteria.json')==plan
else:put(D/'criteria.json',plan)
put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':b})
m=read(A/'실험/manifest.json');m['decision_eligible']=True
m['lineage']['hypothesis_delta']=plan['scope']
m['design'].update(hypothesis='Session state and legal experience authority do not require user_wiki or an additional application HMAC.',primary_metric='All new session/removal contracts pass; no new critical regression failures',success_criteria='; '.join(plan['acceptance']),failure_criteria='Any missing required behavior, new regression failure, scope/state/hash/citation defect or signature dependency rejects.',criteria_frozen_before_run=True)
for arm in m['design']['arms']:
 arm.update(changes='Selected generation44 unchanged' if arm['id']=='baseline' else plan['scope'],controls='Same source generation and scripted transport; no model-quality inference')
m['runs'][0].update(purpose='holdout',selection_rule='Prespecified new synthetic contracts enumerated in criteria plus independent maintained regression suites; no production or external model calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),sha256=None)
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name=plan['dataset'],version='session-contracts-20261007-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting'].update(not_applicable_reason='Source retrieval unchanged; contract audit uses synthetic inputs and the same pinned generation, not a retrieval effectiveness comparison')
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No retrieval policy change or legal-quality measurement'
put(A/'실험/manifest.json',m)
sources=list(b['files'])+['05_TESTS/CONTRACTS/test_genos_main_chat.py','05_TESTS/CONTRACTS/test_unified_legal_agent.py']
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A.relative_to(R)),'--candidate-id','session','--experiment-id',m['experiment_id'],'--arm-id','session','--run-id','run-001']
for f in sources:cmd+=['--source',f]
subprocess.run(cmd,cwd=R,check=True)
S=R/'02_BACKEND/lawrag/research/candidates/adr_0681/session/snapshot'
for f in drift:
 if f!='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py':shutil.copy2(R/b['code_root']/f,S/f)
put(D/'working-drift.json',{'unrelated_pending':drift,'strategy':'Selected MAIN for unrelated serving modules; preserve current workflow no-socket adapter and selectively install only scoped modifications. Preserve pending working modules and their engine pins.'})
print('Criteria frozen; selected MAIN unchanged:',p['release_id'])
