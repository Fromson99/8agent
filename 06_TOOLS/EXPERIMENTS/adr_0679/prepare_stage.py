"""Freeze the reviewed serving inventory; no activation or model call."""
from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0679/integrated'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(R/pointer['manifest_path'])
assert pointer==read(D/'baseline-binding.json')['pointer']
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
stage=A/'artifacts/main-stage';assert not stage.exists();shutil.copytree(R/base['code_root'],stage)
for row in cm['files']:
 target=row['target_path'];p=stage/target;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(code/target,p)
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False})
put(D/'preview-validation.json',{'structural_checks_passed':True,'note':'30 candidate contracts passed, legacy broad gate has exactly same 39 historical fixture/expectation failures on active MAIN and candidate; no activation/quality claim.'})
preview=D/'integration-draft.json'
prepare(R,stage,R/base['data_path'],'investigation-completion-v6-20261007-preview-r2',D/'preview-authorization.json',D/'preview-validation.json',preview)
d=read(preview);binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']};d['candidate']=binding
for row in d['changes']:row['reason']='Complete investigation/assessment/rendering/retry/resume contracts on verified active MAIN; preserve unchanged source, access and feedback dependencies.'
staged=dict(base['files'])
for row in d['changes']:
 if row['after'] is None:staged.pop(row['path'],None)
 else:staged[row['path']]=row['after']
for p,h in staged.items():assert sha(stage/p)==h,p
excluded={row['target_path']:'Non-serving synthetic test or isolated audited ExperimentClient; runner dependency separately frozen' for row in cm['files'] if row['target_path'] not in staged}
receipt={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':pointer['release_manifest_sha256'],'candidate':binding,'staged_files':staged,'excluded_candidate_paths':excluded,'reviewed_changes':d['changes'],'base_code_root':base['code_root'],'stage':str(stage.relative_to(R)),'reason':'Exactly this candidate serving inventory is exercised before selective working-code integration or MAIN activation.'}
put(D/'release-rebase.json',receipt);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};d['rebase_receipt']=ref;put(D/'integration.json',d)
manifest=read(A/'실험/manifest.json');manifest['design']['release_rebase']=ref;put(A/'실험/manifest.json',manifest)
from semantic_runtime.release_integration import check
check(R,{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')},staged,d)
put(D/'bindings.json',{'candidate':str(C.relative_to(R)),'candidate_manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'baseline_code':base['code_root'],'baseline_release':pointer,'stage':str(stage.relative_to(R)),'source_generation':base['data_path'],'active_pointer_hash':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
put(D/'release-freeze.json',{'files':{str(p.relative_to(R)):sha(p) for p in [D/'release-rebase.json',D/'integration.json']}|{str((stage/p).relative_to(R)):h for p,h in staged.items()}})
print(json.dumps({'serving_files':len(staged),'changes':len(d['changes']),'excluded':excluded}))
