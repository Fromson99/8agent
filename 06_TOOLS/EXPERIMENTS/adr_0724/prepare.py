from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0724-source-recovery-boundary-fix';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'02_BACKEND/lawrag/research/candidates/adr_0723/integrated';cm=json.loads((P/'candidate.json').read_text());rev=cm['revisions'][-1];src=P/'revisions'/rev['revision_id']/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'scope':'Fix exact source target registration outside current catalogue, preserve partial batch receipts during accepted-tool resume, normalize failed structural queries, and advance state version after recoverable failure.',
'required':['All38 inherited and reproduced boundary contracts pass; no new legacy failures', 'Off-menu exact targets register only scoped documents and read without KeyError', 'A completed batch target is not acquired again when an accepted interrupted action resumes; partial receipts and original text remain unadopted', 'Known transient acquisition interruption saves the interrupted plan and allows different offered actions', 'Equivalent normalized failed structure query is rejected while a genuinely changed query is allowed', 'Recoverable failure advances state version and records failed chain outcome; unknown/hash/ACL errors still fail closed'],
'external_calls':0,'main_mutation':False,'known_results':'ADR0723 completed Rejected; four reproduced boundary violations are the fixed source. No reused model outputs certify changed code.'}
put(D/'criteria.json',criteria);put(D/'dataset.json',{'version':'v1','cases':[],'type':'Synthetic same-decision interruption and new-request boundaries','required':criteria['required']})
m=json.loads((A/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Immutable decision resume and preserved request boundaries',success_criteria=criteria['required'],failure_criteria='Any state/quote/budget or new regression failure',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:arm.update(changes='Completed0718 exact code' if arm['id']=='baseline' else criteria['scope'],controls='No external model; deterministic synthetic originals, actual native code')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Four reproduced failures plus transient partial acquisition and scoped target rejection, all prior34 and same legacy tests; no model quality comparison',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='Immutable retry boundary synthetic tests',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True);m['llm_policy']['llm_calls']=[]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Ordinary synthetic state contracts; no retrieval effect measurement');m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason'];put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for x in cm['files']:
 if (R/x['target_path']).is_file():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL);C=R/'02_BACKEND/lawrag/research/candidates/adr_0724/integrated'
for x in cm['files']:
 p=x['target_path'];dst=C/'snapshot'/p;dst.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/p,dst)
 if not (R/p).is_file():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',p,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent.json',{'manifest_sha256':sha(P/'candidate.json'),'revision':rev['revision_id'],'files':{x['target_path']:sha(src/x['target_path']) for x in cm['files']}})
print('Prepared isolated0720 synthetic repair')
