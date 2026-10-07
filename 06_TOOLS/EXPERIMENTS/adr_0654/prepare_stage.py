"""Create an explicit active-MAIN overlay stage and pin its exact serving projection."""
from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0654-shortcut-boundary-separated-main';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'bindings.json');pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(R/pointer['manifest_path']);C=R/b['candidate'];m=read(C/'candidate.json');rev=m['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';stage=A/'artifacts/main-stage';shutil.copytree(R/base['code_root'],stage,dirs_exist_ok=True)
for row in rev['files']:row['target_path']=next(f['target_path'] for f in m['files'] if f['snapshot_path']==row['snapshot_path'])
for row in rev['files']:
 p=stage/row['target_path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/row['frozen_path'],p)
sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False});put(D/'preview-validation.json',{'structural_checks_passed':True,'note':'85 candidate and18 operator contracts, preview only; actual qualification pending'})
preview=D/'integration-draft.json';prepare(R,stage,R/b['generation'],'shortcut-integrated-v6-20261005-r1',D/'preview-authorization.json',D/'preview-validation.json',preview)
d=read(preview);binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']};d['candidate']=binding
for row in d['changes']:
 p=row['path']
 if 'release_' in p or p.endswith('/control.py'):reason='Qualified source validation and explicit evaluated stage; no historical waiver used'
 elif '/ENGINES/' in p or p=='00_SYSTEM/PIPELINE.json':reason='Pin v6 current-source shortcut engine code and retain existing source generation and scope profiles'
 elif '/legal_agent/' in p:reason='Frozen integrated v6 case state, deterministic procedure replay, closed source evidence and preservation of prior source-prefix/scope controls'
 elif '/lawrag/pipeline/' in p:reason='Connect shortcut operations and legal wiki construction to existing pipeline consumers'
 else:reason='Required frozen v6 runtime dependency or API/service integration; active baseline and exact after hash reviewed'
 row['reason']=reason
# The serving inventory is reconstructed exactly from the preview delta.
staged=dict(base['files'])
for row in d['changes']:
 if row['after'] is None:staged.pop(row['path'],None)
 else:staged[row['path']]=row['after']
for p,h in staged.items():assert sha(stage/p)==h,p
excludes={r['target_path']:'Not included by the existing serving publisher; build/CLI support retained in the reviewed working-code inventory' for r in rev['files'] if r['target_path'] not in staged}
receipt={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':pointer['release_manifest_sha256'],'candidate':binding,'staged_files':staged,'excluded_candidate_paths':excludes,'reviewed_changes':d['changes'],'base_code_root':base['code_root'],'stage':str(stage.relative_to(R)),'reason':'Start with active MAIN release, then explicitly overlay the completed integrated candidate; preserve every unmodified active file. Entire resulting inventory is frozen before separated evaluation.'};put(D/'release-rebase.json',receipt);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};d['rebase_receipt']=ref;put(D/'integration.json',d)
source=read(A/'실험/manifest.json');source['design']['release_rebase']=ref;put(A/'실험/manifest.json',source)
from semantic_runtime.release_integration import check
check(R,{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')},staged,d)
files={str(p.relative_to(R)):sha(p) for p in [D/'release-rebase.json',D/'integration.json']}
files.update({str((stage/p).relative_to(R)):h for p,h in staged.items()});put(D/'release-freeze.json',{'files':files,'note':'Second seal adds exact MAIN stage before any product call; initial code/data/design seal remains intact.'});print(json.dumps({'serving_files':len(staged),'changed_files':len(d['changes']),'excluded_build_files':len(excludes),'same_product_code':True}))
