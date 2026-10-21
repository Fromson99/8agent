from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
inventory=read(D/'serving-files.json');bindings=[];files={};changes={}
for arm in ('rebased','bridged'):
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0924'/arm;S=C/'snapshot'
 names=set(inventory)
 if arm=='bridged':
  new='02_BACKEND/semantic_runtime/legal_agent/investigation_leads.py';names.add(new)
  proc=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',new,'--upstream-state','absent'],capture_output=True,text=True)
  assert proc.returncode==0,proc.stdout+proc.stderr
 for n in names:
  if n.endswith('.py'):compile((S/n).read_bytes(),n,'exec')
 for p in (S/'02_BACKEND/workflow').rglob('manifest.json'):
  v=read(p)
  for n in v.get('files',{}):v['files'][n]=sha(S/'02_BACKEND/workflow'/n)
  put(p,v)
 for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
  v=read(p)
  if not isinstance(v.get('files'),dict):continue
  if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in v['files']:
   v['files']['02_BACKEND/semantic_runtime/legal_agent/connected_exploration.py']=''
   if arm=='bridged':v['files']['02_BACKEND/semantic_runtime/legal_agent/investigation_leads.py']=''
  for n in v['files']:v['files'][n]=sha(S/n)
  put(p,v)
 p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
 for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
 put(p,v)
 for command in ('refresh','freeze','validate'):
  proc=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],capture_output=True,text=True)
  assert proc.returncode==0,(command,proc.stdout,proc.stderr)
 cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
 candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
  'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':arm,'arm_id':arm,
  'experiment_id':'ADR-0924-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
 binding={'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in sorted(names)},'candidate':candidate}
 put(D/(arm+'-binding.json'),binding);bindings.append(candidate)
 files.update({str((code/n).relative_to(R)):h for n,h in binding['serving_files'].items()})
 before=read(D/'working-before.json')
 changes[arm]=[{'path':n,'working':before.get(n),'candidate':sha(code/n)} for n in sorted(names) if before.get(n)!=sha(code/n)]
put(D/'changes.json',changes)
tests=['06_TOOLS/EXPERIMENTS/adr_0924/test_leads.py','06_TOOLS/EXPERIMENTS/adr_0922/test_connected_exploration.py','06_TOOLS/EXPERIMENTS/adr_0922/test_normalized_current.py','06_TOOLS/EXPERIMENTS/adr_0844/test_sources.py','06_TOOLS/EXPERIMENTS/adr_0845/test_qualification.py','05_TESTS/CONTRACTS/test_reference_decision_continuity.py','05_TESTS/CONTRACTS/test_read_choice_input_preservation.py','05_TESTS/CONTRACTS/test_output_contract_recovery.py','05_TESTS/CONTRACTS/test_structure_reading.py','05_TESTS/test_definition_entry_integration.py','06_TOOLS/EXPERIMENTS/adr_0915/test_api.py']
put(D/'execution-plan.json',{'tests':tests,'live_order':['rebased','bridged'],'cases':['leverage-comparison'],'runs_per_arm':1,'legacy_deselection':'test_wire_shape_removes_action_cross_product_but_original_rejects_wrong_target: unchanged MAIN88 failure already preserved in ADR0921'})
paths=[*T.glob('*.py'),*D.glob('*.json'),*R.glob('05_TESTS/**/*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_08*/test*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_0922/test*.py'),R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/adr_0915/test_api.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
generation=R/read(D/'baseline.json')['manifest']['data_path']
paths += [generation/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'candidates':bindings})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=bindings);put(A/'실험/manifest.json',m)
print('Frozen both explicit candidates and tests; selected MAIN unchanged.')
