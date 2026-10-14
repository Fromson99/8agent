from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0720-immutable-decision-retry-resume';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired';cm=json.loads((P/'candidate.json').read_text());rev=cm['revisions'][-1];src=P/'revisions'/rev['revision_id']/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'scope':'Same decision retry restores exact original view/actions even after rejection events change current presentation; already attempted interrupted repair becomes bounded unresolved with no third physical call; new user request gets fresh gap/progress state while keeping prior history and source adoption.',
 'required':['Interrupted repair and restart must not raise stale presentation500','Same-epoch cached repair validates against original immutable view and source binding','No third attempt when transport outcome unknown','Accepted tool resume keeps original before/data and request deadline','New request resets gap reopen history without deleting old audit trail','All20 prior invariants and all previously passing legacy checks remain valid'],
 'external_calls':0,'main_mutation':False,'known_results':'ADR0719 model run already started; its outputs cannot certify this changed candidate. New separate qualification required.'}
put(D/'criteria.json',criteria);put(D/'dataset.json',{'version':'v1','cases':[],'type':'Synthetic same-decision interruption and new-request boundaries','required':criteria['required']})
m=json.loads((A/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Immutable decision resume and preserved request boundaries',success_criteria=criteria['required'],failure_criteria='Any state/quote/budget or new regression failure',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:arm.update(changes='Completed0718 exact code' if arm['id']=='baseline' else criteria['scope'],controls='No external model; deterministic synthetic originals, actual native code')
m['runs'][0].update(arm_ids=['resumed'],selection_rule='Synthetic interruption plus prior20 and same legacy tests; no model quality comparison',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='Immutable retry boundary synthetic tests',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True);m['llm_policy']['llm_calls']=[]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Ordinary synthetic state contracts; no retrieval effect measurement');m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason'];put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','resumed','--experiment-id',m['experiment_id'],'--arm-id','resumed','--run-id','run-001']
for x in cm['files']:
 if (R/x['target_path']).is_file():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL);C=R/'02_BACKEND/lawrag/research/candidates/adr_0720/resumed'
for x in cm['files']:
 p=x['target_path'];dst=C/'snapshot'/p;dst.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/p,dst)
 if not (R/p).is_file():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',p,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent.json',{'manifest_sha256':sha(P/'candidate.json'),'revision':rev['revision_id'],'files':{x['target_path']:sha(src/x['target_path']) for x in cm['files']}})
print('Prepared isolated0720 synthetic repair')
