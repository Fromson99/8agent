from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0911-tagged-navigation-decision';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0911/tagged';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();before=read(D/'working-before.json');active=read(D/'baseline.json')['active_release'];products={'02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('decision_projection','law_navigation')};changed=set(products)
for n in products:compile((S/n).read_text(),n,'exec')
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p);used=products&v.get('files',{}).keys()
 if used:
  for n in used:v['files'][n]=sha(S/n)
  put(p,v);changed.add(str(p.relative_to(S)))
p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():
 if e['manifest'] in changed:e['sha256']=sha(S/e['manifest'])
put(p,v);changed.add('00_SYSTEM/PIPELINE.json');assert {n for n,h in before.items() if sha(S/n)!=h}==changed
put(D/'changes.json',[{'path':n,'before':before[n],'after':sha(S/n)} for n in sorted(changed)])
for command in ('refresh','freeze','validate'):
 v=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],capture_output=True,text=True);assert v.returncode==0,(v.stdout,v.stderr)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';b={'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in active['files']},'candidate':{'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}};put(D/'tagged-binding.json',b)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0910/run_tests.py').read_text().replace('ADR-0910-explicit-navigation-intent','ADR-0911-tagged-navigation-decision').replace("intent-binding.json","tagged-binding.json");(T/'run_tests.py').write_text(s)
plan=read(R/'04_EXPERIMENTS/ADR/ADR-0910-explicit-navigation-intent/artifacts/design/execution-plan.json');plan['tests']=[n.replace('adr_0910/test_intent.py','adr_0911/test_tagged.py').replace('adr_0910/test_api.py','adr_0911/test_api.py') for n in plan['tests']];plan['live_order']=['tagged'];put(D/'execution-plan.json',plan)
files={str((code/n).relative_to(R)):sha(code/n) for n in before}
parentf=read(R/'04_EXPERIMENTS/ADR/ADR-0910-explicit-navigation-intent/artifacts/design/freeze.json')
for n,h in parentf['files'].items():
 if n.startswith(('05_TESTS/','06_TOOLS/EXPERIMENTS/adr_0895/','06_TOOLS/EXPERIMENTS/adr_0885/','06_TOOLS/EXPERIMENTS/adr_0892/','06_TOOLS/EXPERIMENTS/adr_0832/')) or n in ('06_TOOLS/EXPERIMENTS/resource_guard.py','02_BACKEND/lawrag/research/experiment_client.py','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') or n.startswith(active['data_path']+'/'):
  assert sha(R/n)==h,n;files[n]=h
for p in [*T.glob('*.py'),*D.glob('*.json'),R/'06_TOOLS/EXPERIMENTS/adr_0910/test_intent.py']:files[str(p.relative_to(R))]=sha(p)
entry={**b['candidate'],'candidate_id':'tagged','arm_id':'tagged','experiment_id':'ADR-0911-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'candidates':[entry]})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[entry]);put(A/'실험/manifest.json',m);print('Frozen tagged candidate, tests, one known public request; no working product changes')
