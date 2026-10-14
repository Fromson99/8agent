from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();base=read(D/'baseline.json');codes={'baseline':base['manifest']['code_root']};bindings=[]
for arm in ['compact-display']:
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0704'/arm
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True)
 cm=read(C/'candidate.json');rev=cm['revisions'][-1];codes[arm]=str((C/'revisions'/rev['revision_id']/'snapshot').relative_to(R))
 bindings.append({'candidate_id':arm,'arm_id':arm,'experiment_id':'ADR-0704-experiment-v1','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0704/audit.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0704/audit.py')})
code=R/codes['compact-display'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
prepare(R,code,R/base['manifest']['data_path'],'structure-display-frozen-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
integration=read(D/'integration-draft.json');binding={k:bindings[-1][k] for k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')};integration['candidate']=binding
for row in integration['changes']:
 row['reason']='Compact public progress, preserve full private judgment log and count physical model transport timings. Product semantics unchanged.'
files=dict(base['manifest']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for name,h in files.items():assert sha(code/name)==h,name
cm=read(R/binding['manifest_path'])
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Synthetic contract test, research-only client or build fixture' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':integration['changes'],'base_code_root':base['manifest']['code_root'],'stage':codes['compact-display'],'reason':'Frozen complete package verified in the same data/profile/service path; reviewed scoped edits will be installed without overwriting unrelated working files.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,integration)
put(D/'bindings.json',{'codes':codes,'stage':codes['compact-display'],'baseline_code':codes['baseline'],'source_generation':base['manifest']['data_path'],'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=bindings;m['design']['release_rebase']=ref
put(A/'실험/manifest.json',m)
paths=list(D.glob('*.json'))+[R/b['manifest_path'] for b in bindings]+[R/'06_TOOLS/EXPERIMENTS/adr_0704/audit.py',R/'06_TOOLS/EXPERIMENTS/adr_0704/run_contracts.py',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
frozen={str(p.relative_to(R)):sha(p) for p in paths}
for root in codes.values():
 frozen.update({str(p.relative_to(R)):sha(p) for p in (R/root).rglob('*') if p.is_file() and '__pycache__' not in p.parts})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':codes['compact-display'],'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen complete package:',len(files),'serving files; prospective model-free matrix not started')
