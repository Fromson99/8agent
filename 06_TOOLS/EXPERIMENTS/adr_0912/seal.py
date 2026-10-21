from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();before=read(D/'working-before.json');active=read(D/'baseline.json')['active_release']
for arm in ('baseline','answer-first'):
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0912'/(arm+'-r1');S=C/'snapshot'
 if arm=='answer-first':
  products={'02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('law_candidates','law_navigation','evidence_inventory','completion_execution')}|{'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'};changed=set(products)
  for n in products:
   if n.endswith('.py'):compile((S/n).read_text(),n,'exec')
  for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
   v=read(p);used=products&v.get('files',{}).keys()
   if used:
    for n in used:v['files'][n]=sha(S/n)
    put(p,v);changed.add(str(p.relative_to(S)))
  p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
  for e in v['engines'].values():
   if e['manifest'] in changed:e['sha256']=sha(S/e['manifest'])
  put(p,v);changed.add('00_SYSTEM/PIPELINE.json')
  assert {n for n,h in before.items() if sha(S/n)!=h}==changed
  put(D/'changes.json',[{'path':n,'before':before[n],'after':sha(S/n)} for n in sorted(changed)])
 for command in ('refresh','freeze','validate'):
  v=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],capture_output=True,text=True)
  assert v.returncode==0,(command,v.stdout,v.stderr)
 cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
 put(D/(arm+'-binding.json'),{'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in active['files']},'candidate':{'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
(T/'run_tests.py').write_text("from pathlib import Path\nimport hashlib,json,os,runpy\nR=Path(__file__).resolve().parents[3]\nD=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup/artifacts/design'\nf=json.loads((D/'freeze.json').read_text())\nfor n,h in f['files'].items():\n assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h,n\nos.environ['TASK_TEST_CODE_ROOT']=str(R/json.loads((D/'answer-first-binding.json').read_text())['code_root'])\nrunpy.run_path(str(R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py'),run_name='__main__')\n")
tests=[str((T/'test_api.py').relative_to(R)),str((T/'test_policy.py').relative_to(R)),
 '05_TESTS/CONTRACTS/test_output_contract_recovery.py','05_TESTS/CONTRACTS/test_reference_decision_continuity.py',
 '05_TESTS/CONTRACTS/test_read_choice_input_preservation.py','05_TESTS/CONTRACTS/test_unified_legal_agent.py',
 '05_TESTS/CONTRACTS/test_team_session_identity.py']
put(D/'execution-plan.json',{'tests':tests,'pytest_args':[],'live_order':['baseline','answer-first'],'scenarios':['cm-001','cm-033'],'runs_per_scenario':1,'product_inputs':'Public-only request and follow-up without gold; stable same-session ID; duplicate no-call check.'})
files={};candidates=[]
for arm in ('baseline','answer-first'):
 b=read(D/(arm+'-binding.json'));code=R/b['code_root'];files.update({str((code/n).relative_to(R)):sha(code/n) for n in before})
 candidates.append({**b['candidate'],'candidate_id':arm+'-r1','arm_id':arm,'experiment_id':'ADR-0912-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')})
for p in [*T.glob('*.py'),*D.glob('*.json'),* (R/'05_TESTS/CONTRACTS').glob('*.py'),R/'05_TESTS/conftest.py',R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py',R/'06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py',R/'06_TOOLS/EXPERIMENTS/adr_0832/test_delivery.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',*[R/active['data_path']/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]]:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'candidates':candidates})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates);put(A/'실험/manifest.json',m)
print('Frozen baseline and intent rev-001; tests and one sequential live request per arm; MAIN unchanged')
