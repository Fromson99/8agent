from pathlib import Path
import json,hashlib,sys,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0805-mechanical-wire-coverage';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0805/connected'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
# Use the already frozen, tested revision; do not mutate history.
base=read(D/'baseline.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
fullbinding={**binding,'candidate_id':'connected','arm_id':'connected','experiment_id':'ADR-0805-experiment-v1','run_ids':['run-001'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0805/audit_pinned.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0805/audit_pinned.py')}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True})
prepare(R,code,R/read(D/'data-binding.json')['path'],'workflow-evidence-preview-'+rev['revision_id'],D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
integration=read(D/'integration-draft.json');integration['candidate']=binding
for row in integration['changes']:row['reason']='Committed evidence handoff, current bundles, bounded presentation and exact report/UI; source and selection preserved.'
files=dict(base['manifest']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for name,h in files.items():assert sha(code/name)==h,name
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Synthetic contract fixture, not served' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':integration['changes'],'base_code_root':base['manifest']['code_root'],'stage':str(code.relative_to(R)),'reason':'MAIN74 serving baseline preserved; selected scope, immutable sources and all unrelated serving files retained.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,integration)
m=read(A/'실험/manifest.json');m['dataset']['sha256']=sha(D/'criteria.json');m['design']['code_isolation']['candidates']=[fullbinding];m['design']['release_rebase']=ref;put(A/'실험/manifest.json',m)
paths=list((R/'06_TOOLS/EXPERIMENTS/adr_0805').glob('*.py'))+list(D.glob('*.json'))+[C/'candidate.json',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']

paths += [R/'02_BACKEND/lawrag/research/experiment_client.py']
paths += [p for folder in ('02_BACKEND/lawrag/core','02_BACKEND/lawrag/pipeline','02_BACKEND/lawrag/platform') for p in (R/folder).rglob('*.py')]
frozen={str(p.relative_to(R)):sha(p) for p in paths};frozen.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen',len(files),'serving files; changes',len(integration['changes']))
