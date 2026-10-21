from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0922-term-phrase-current-reference';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
active={**read(D/'baseline.json')['manifest'],'files':read(D/'parent-binding.json')['serving_files']};C=R/'02_BACKEND/lawrag/research/candidates/adr_0922/normalized';S=C/'snapshot'
new='02_BACKEND/semantic_runtime/legal_agent/connected_exploration.py'
products={n for n,h in active['files'].items() if sha(S/n)!=h and n.endswith('.py')}|{new}
for n in products:compile((S/n).read_text(),n,'exec')
changed=set(products)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p);used=products&v.get('files',{}).keys()
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in v.get('files',{}):used=used|{new}
 if used:
  for n in used:v['files'][n]=sha(S/n)
  put(p,v);changed.add(str(p.relative_to(S)))
p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():
 if e['manifest'] in changed:e['sha256']=sha(S/e['manifest'])
put(p,v);changed.add('00_SYSTEM/PIPELINE.json')
actual={n for n,h in active['files'].items() if sha(S/n)!=h}|{new}
assert actual==changed,(actual-changed,changed-actual)
put(D/'changes.json',[{'path':n,'before':active['files'].get(n),'after':sha(S/n)} for n in sorted(changed)])
for command in ('refresh','freeze','validate'):
 p=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],capture_output=True,text=True)
 assert p.returncode==0,(command,p.stdout,p.stderr)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
b={'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in set(active['files'])|{new}},'candidate':{'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(D/'normalized-binding.json',b)
tests=[str((T/'test_normalized_current.py').relative_to(R)),str((T/'test_connected_exploration.py').relative_to(R)),'05_TESTS/CONTRACTS/test_reference_decision_continuity.py','05_TESTS/CONTRACTS/test_read_choice_input_preservation.py','05_TESTS/CONTRACTS/test_output_contract_recovery.py','05_TESTS/CONTRACTS/test_structure_reading.py','05_TESTS/test_definition_entry_integration.py','06_TOOLS/EXPERIMENTS/adr_0915/test_api.py']
put(D/'execution-plan.json',{'tests':tests,'live_order':['normalized'],'runs_per_arm':1,'cases':['leverage-comparison']})
files={}
for arm in ('normalized',):
 binding=read(D/(arm+'-binding.json'));files.update({str((R/binding['code_root']/n).relative_to(R)):h for n,h in binding['serving_files'].items()})
paths=[*T.glob('*.py'),*D.glob('*.json'),*R.glob('05_TESTS/**/*.py'),R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py',R/'06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py',R/'06_TOOLS/EXPERIMENTS/adr_0832/test_delivery.py',R/'06_TOOLS/EXPERIMENTS/adr_0915/test_api.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',*[R/active['data_path']/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]]
for p in paths:files[str(p.relative_to(R))]=sha(p)
candidate={**b['candidate'],'candidate_id':'normalized','arm_id':'normalized','experiment_id':'ADR-0922-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'candidates':[candidate]})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[candidate]);put(A/'실험/manifest.json',m)
print('Frozen '+rev['revision_id']+'; '+str(len(products))+' product files, '+str(len(tests))+' test modules; MAIN88 unchanged.')
