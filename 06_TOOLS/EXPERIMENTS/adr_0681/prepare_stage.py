"""Prepare exact frozen serving inventory without activation."""
import json,hashlib,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0681/session'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'baseline.json');p=b['pointer'];assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False})
put(D/'preview-validation.json',{'structural_checks_passed':True,'note':'Unsigned session, projection and native JSON/SSE development contracts passed; this read-only preview does not activate MAIN.'})
prepare(R,code,R/b['manifest']['data_path'],'session-runtime-v6-20261007-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
d=read(D/'integration-draft.json');binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']};d['candidate']=binding
for row in d['changes']:row['reason']='Remove user_wiki and additional application HMAC; preserve session/shortcut/legal authority and the current no-socket workflow adapter.'
files=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for f,h in files.items():assert sha(code/f)==h,f
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':p['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{row['target_path']:'Non-serving synthetic contract' for row in cm['files'] if row['target_path'] not in files},'reviewed_changes':d['changes'],'base_code_root':b['manifest']['code_root'],'stage':str(code.relative_to(R)),'reason':'Frozen release inventory is evaluated directly; unrelated pending working changes are preserved outside this release.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};d['rebase_receipt']=ref;put(D/'integration.json',d)
m=read(A/'실험/manifest.json');m['design']['release_rebase']=ref
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'session','experiment_id':m['experiment_id'],'arm_id':'session','run_ids':['run-001'],'manifest_path':binding['manifest_path'],'manifest_sha256':binding['manifest_sha256'],'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0681/run_contracts.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0681/run_contracts.py')}])
put(A/'실험/manifest.json',m)
from semantic_runtime.release_integration import check
check(R,{'pointer':p,'pointer_sha256':b['pointer_sha256']},files,d)
put(D/'freeze.json',{'files':{str(x.relative_to(R)):sha(x) for x in [D/'criteria.json',D/'release-rebase.json',D/'integration.json',C/'candidate.json',R/'06_TOOLS/EXPERIMENTS/adr_0681/run_contracts.py']},'serving_files':files,'code_root':str(code.relative_to(R))})
print('Frozen serving files:',len(files),'changes:',len(d['changes']))
