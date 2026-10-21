from pathlib import Path
import json,hashlib,subprocess,sys,datetime,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0930-connected-read-review-fix';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
if (D/'freeze.json').exists():
 assert not (A/'artifacts/sequence.jsonl').exists()
 history=D/'prelive-history';history.mkdir(exist_ok=True);h=history/f'{len(list(history.iterdir()))+1:03d}';h.mkdir()
 for p in D.glob('*.json'):shutil.copy2(p,h/p.name)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0930/fixed';S=C/'snapshot';names=read(D/'serving-files.json')
for p in (S/'02_BACKEND/workflow').rglob('manifest.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(S/'02_BACKEND/workflow'/n)
 put(p,v)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not isinstance(v.get('files'),dict):continue
 for n in v['files']:v['files'][n]=sha(S/n)
 put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
for w in v.get('workflows',{}).get('registered',[]):w['sha256']=sha(S/w['manifest'])
put(p,v)
for cmd in ('refresh','freeze','validate'):
 proc=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',cmd,str(C)],capture_output=True,text=True)
 assert proc.returncode==0,(cmd,proc.stdout,proc.stderr)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':'fixed','arm_id':'fixed','experiment_id':'ADR-0930-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
binding={'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in names},'candidate':candidate,'release_id':'adr0930-fixed','generation':89}
put(D/'fixed-binding.json',binding)
base=read(D/'baseline.json')['manifest'];put(D/'changes.json',[{'path':n,'before':base['files'][n],'after':sha(code/n)} for n in names if base['files'][n]!=sha(code/n)])
tests=['06_TOOLS/EXPERIMENTS/adr_0930/test_fixes.py','06_TOOLS/EXPERIMENTS/adr_0930/test_leads_compact.py','06_TOOLS/EXPERIMENTS/adr_0922/test_connected_exploration.py','06_TOOLS/EXPERIMENTS/adr_0922/test_normalized_current.py','06_TOOLS/EXPERIMENTS/adr_0930/test_sources_compact.py','06_TOOLS/EXPERIMENTS/adr_0845/test_qualification.py','05_TESTS/CONTRACTS/test_reference_decision_continuity.py','05_TESTS/CONTRACTS/test_read_choice_input_preservation.py','05_TESTS/CONTRACTS/test_output_contract_recovery.py','05_TESTS/CONTRACTS/test_structure_reading.py','05_TESTS/test_definition_entry_integration.py','06_TOOLS/EXPERIMENTS/adr_0915/test_api.py']
put(D/'tests.json',{'tests':tests,'excluded_existing':['test_wire_shape_removes_action_cross_product_but_original_rejects_wrong_target','test_zero_read_source_handoff_is_valid_api_result']})
files={str((code/n).relative_to(R)):sha(code/n) for n in names}
paths=[*T.glob('*.py'),*(p for p in D.glob('*.json') if p.name!='freeze.json'),*R.glob('05_TESTS/**/*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_08*/test*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_092*/test*.py'),R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
paths += [R/base['data_path']/n for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
for row in read(D/'inherited.json').values():paths += [R/row['root']/n for n in row['files']]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'candidates':[candidate],'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[candidate]);put(A/'실험/manifest.json',m)
print('Frozen',rev['revision_id'],'changed files',len(read(D/'changes.json')))
