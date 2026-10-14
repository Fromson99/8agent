from pathlib import Path
import json,hashlib,sys,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0750-focused-recovery-public-qualification';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0750/integrated'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
base=read(D/'baseline.json')
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
assert read(A/'artifacts/contract-result.json')['all_new_contracts_pass']
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
fullbinding={**binding,'candidate_id':'integrated','arm_id':'integrated','experiment_id':'ADR-0750-experiment-v1','run_ids':['run-001'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0750/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0750/run_case.py')}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
prepare(R,code,R/base['manifest']['data_path'],'request-repair-frozen-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
integration=read(D/'integration-draft.json');integration['candidate']=binding
for row in integration['changes']:row['reason']='Reviewed four fixes: reversible actual navigation inputs, request-grounded additional exploration, scoped heading failure, and source-ID-bound v8 single-content norms and material-gap recovery. MAIN52 functions retained; no cache change.'
files=dict(base['manifest']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for name,h in files.items():assert sha(code/name)==h,name
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Synthetic fixture or research-only client' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':integration['changes'],'base_code_root':base['manifest']['code_root'],'stage':str(code.relative_to(R)),'reason':'Unchanged completed implementation evaluated as a complete release; only reviewed changed files installed if all qualification gates pass.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,integration)
put(D/'bindings.json',{'codes':{'baseline':base['manifest']['code_root'],'integrated':str(code.relative_to(R))},'stage':str(code.relative_to(R)),'baseline_code':base['manifest']['code_root'],'source_generation':base['manifest']['data_path'],'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[fullbinding];m['design']['release_rebase']=ref;put(A/'실험/manifest.json',m)
paths=[R/'06_TOOLS/EXPERIMENTS/adr_0750/audit.py',R/'06_TOOLS/EXPERIMENTS/adr_0750/repeat_ledger.py']+list(D.glob('*.json'))+[C/'candidate.json',R/'06_TOOLS/EXPERIMENTS/adr_0750/run_case.py',R/'06_TOOLS/EXPERIMENTS/adr_0750/run_all.py',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
frozen={str(p.relative_to(R)):sha(p) for p in paths}
frozen.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen',len(files),'serving files, reviewed changes',len(integration['changes']))
