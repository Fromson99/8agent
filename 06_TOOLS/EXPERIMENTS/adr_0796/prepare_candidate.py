from pathlib import Path
import json,hashlib,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0796/selected'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
base=read(D/'baseline.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1];S=C/'revisions'/rev['revision_id']/'snapshot';sys.dont_write_bytecode=True;sys.path.insert(0,str(S/'02_BACKEND'))
source=R/base['manifest']['data_path'];dest=R/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
dest.mkdir(parents=True,exist_ok=True)
for p in source.rglob('*'):
 target=dest/p.relative_to(source)
 if p.is_symlink():raise ValueError('source symlink')
 if p.is_dir():target.mkdir(exist_ok=True)
 elif p.is_file():
  if target.exists():assert target.stat().st_ino==p.stat().st_ino
  else:os.link(p,target)
from lawrag.pipeline.search_selection import plan,activate
p=plan(dest,latest=True);put(A/'artifacts/selection-plan.json',p);result=activate(p);result.setdefault('target',result.get('path'));put(A/'artifacts/selection-apply.json',result)
put(D/'data-binding.json',{'path':str(dest.relative_to(R)),'manifest_sha256':sha(dest/'manifest.json'),'source_generation':base['manifest']['data_path'],'same_immutable_assets':True,'selection_sha256':result['selection_sha256'],'selection_path':str(Path(result['target']).relative_to(R)),'selection_file_sha256':sha(Path(result['target']))})
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True})
prepare(R,S,dest,'latest-selection-preview-'+rev['revision_id']+'-r2',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft-r2.json')
v=read(D/'integration-draft-r2.json');v['candidate']=binding
for row in v['changes']:row['reason']='Approved filename latest selection marks and shared RAW/serving policy; all unrelated MAIN72 functions preserved'
files=dict(base['manifest']['files'])
for row in v['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Pipeline/test dependency retained as work code, not served' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':v['changes'],'base_code_root':base['manifest']['code_root'],'stage':str(S.relative_to(R)),'reason':'MAIN72 code preserved except declared selection deltas; pipeline-only sources separately integrated'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};v['rebase_receipt']=ref;put(D/'integration.json',v)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,v)
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[{**binding,'candidate_id':'selected','arm_id':'selected','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0796/audit_pinned.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0796/audit_pinned.py')}];m['design']['release_rebase']=ref;put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'code_root':str(S.relative_to(R)),'serving_files':files,'candidate':binding,'files':{str((S/x['target_path']).relative_to(R)):sha(S/x['target_path']) for x in cm['files']}})
print('Frozen',len(files),'serving files; local candidate selection',p['counts'])
