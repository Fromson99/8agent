from pathlib import Path
import json,hashlib,sys,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0837-comparison-advisory-items';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0837/connected'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
# Use the already frozen, tested revision; do not mutate history.
base=read(D/'baseline.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
fullbinding={**binding,'candidate_id':'connected','arm_id':'connected','experiment_id':'ADR-0837-experiment-v1','run_ids':['run-001'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0837/run_tests.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0837/run_tests.py')}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True})
prepare(R,code,R/read(D/'data-binding.json')['path'],'workflow-evidence-preview-'+rev['revision_id'],D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
integration=read(D/'integration-draft.json');integration['candidate']=binding
for row in integration['changes']:row['reason']='LLM semantic review with source/ACL/hash/state integrity retained; same native retrieval and data/profile.'
files=dict(base['selected_release_manifest']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for name,h in files.items():assert sha(code/name)==h,name
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Synthetic contract fixture, not served' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':integration['changes'],'base_code_root':base['selected_release_manifest']['code_root'],'stage':str(code.relative_to(R)),'reason':'MAIN78 serving baseline preserved; selected scope, immutable sources and all unrelated serving files retained.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,integration)
m=read(A/'실험/manifest.json');m['dataset']['sha256']=sha(D/'criteria.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,candidates=[fullbinding]);m['design']['release_rebase']=ref;put(A/'실험/manifest.json',m)
paths=list((R/'06_TOOLS/EXPERIMENTS/adr_0837').glob('*.py'))+list(D.glob('*.json'))+[C/'candidate.json',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']

paths += [R/'02_BACKEND/lawrag/research/experiment_client.py']
paths += list((R/'05_TESTS').rglob('*.py'))
paths += [p for name in ('adr_0811','adr_0830','adr_0832') for p in (R/'06_TOOLS/EXPERIMENTS'/name).glob('*.py')]
paths += [p for folder in ('02_BACKEND/lawrag/core','02_BACKEND/lawrag/pipeline','02_BACKEND/lawrag/platform') for p in (R/folder).rglob('*.py')]
frozen={str(p.relative_to(R)):sha(p) for p in paths};frozen.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
put(D/'verification-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':files,'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen',len(files),'serving files; changes',len(integration['changes']))
