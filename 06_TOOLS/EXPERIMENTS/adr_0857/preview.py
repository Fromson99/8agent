from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0857-host-assembly-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True})
prepare(R,C,R/read(D/'data-binding.json')['path'],'host-assembled-probe-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
b=read(D/'baseline.json');integration=read(D/'integration-draft.json');integration['candidate']=f['candidate']
for row in integration['changes']:row['reason']='Shared basis lifecycle and preserved current working dependencies, including concurrent Oracle DP service merge; finite technical verification, no legal accuracy certification.'
files=dict(b['release']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for n,h in files.items():assert sha(C/n)==h,n
cm=read(R/f['candidate']['manifest_path'])
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['candidate'],
 'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Build/collection CLI dependencies tested and integrated separately; not part of runtime serving tree' for x in cm['files'] if x['target_path'] not in files},
 'reviewed_changes':integration['changes'],'base_code_root':b['release']['code_root'],'stage':str(C.relative_to(R)),'reason':'MAIN81 sources/profile retained; current working modifications preserved and shared lifecycle added.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':b['pointer'],'pointer_sha256':b['pointer_sha256']},files,integration)
put(D/'verification-binding.json',{'code_root':f['code_root'],'serving_files':files,'candidate':f['candidate']})
m=read(A/'실험/manifest.json');m['design']['release_rebase']=ref;put(A/'실험/manifest.json',m)
print('Serving files',len(files),'reviewed deltas',len(integration['changes']))
