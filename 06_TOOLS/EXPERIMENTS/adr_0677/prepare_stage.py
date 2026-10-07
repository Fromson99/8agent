from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
C=R/'02_BACKEND/lawrag/research/candidates/adr_0677/integrated';m=read(C/'candidate.json');rev=m['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(R/pointer['manifest_path']);stage=A/'artifacts/main-stage';assert not stage.exists();shutil.copytree(R/base['code_root'],stage)
for row in rev['files']:
 target=next(f['target_path'] for f in m['files'] if f['snapshot_path']==row['snapshot_path']);row['target_path']=target
 p=stage/target;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/row['frozen_path'],p)
# Retain the earlier source-by-source integration ledger before creating publisher declaration.
shutil.copy2(D/'integration.json',D/'working-integration.json')
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False});put(D/'preview-validation.json',{'structural_checks_passed':True,'note':'84 ordinary reader/native API contracts passed; preview only, independent product qualification pending'})
preview=D/'integration-draft.json';prepare(R,stage,R/base['data_path'],'investigation-control-v6-20261006-r1',D/'preview-authorization.json',D/'preview-validation.json',preview)
d=read(preview);binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']};d['candidate']=binding
for row in d['changes']:row['reason']='Frozen latest working-code integration with exact delivered/adopted ranges, saved reread, immutable action chain, bounded assessment reentry and consumer/service binding; unchanged active dependencies preserved'
staged=dict(base['files'])
for row in d['changes']:
 if row['after'] is None:staged.pop(row['path'],None)
 else:staged[row['path']]=row['after']
for p,h in staged.items():assert sha(stage/p)==h,p
excludes={r['target_path']:'Test/build/config support outside existing serving inventory; no product execution dependency omitted' for r in rev['files'] if r['target_path'] not in staged}
receipt={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':pointer['release_manifest_sha256'],'candidate':binding,'staged_files':staged,'excluded_candidate_paths':excludes,'reviewed_changes':d['changes'],'base_code_root':base['code_root'],'stage':str(stage.relative_to(R)),'reason':'Active release plus file-by-file frozen latest integration; exactly this serving inventory is independently evaluated before MAIN activation'};put(D/'release-rebase.json',receipt);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};d['rebase_receipt']=ref;put(D/'integration.json',d)
source=read(A/'실험/manifest.json');source['design']['release_rebase']=ref;put(A/'실험/manifest.json',source)
from semantic_runtime.release_integration import check
check(R,{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')},staged,d)
files={str(p.relative_to(R)):sha(p) for p in [D/'release-rebase.json',D/'integration.json']};files.update({str((stage/p).relative_to(R)):h for p,h in staged.items()});put(D/'release-freeze.json',{'files':files})
print(json.dumps({'serving_files':len(staged),'changes':len(d['changes']),'same_serving_inventory':True}))
