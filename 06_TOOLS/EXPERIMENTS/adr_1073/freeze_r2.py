from pathlib import Path
import hashlib,json,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design-r2';C=R/'02_BACKEND/lawrag/research/candidates/adr_1073/sql-main-r2'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';base=read(D/'baseline.json');prep=read(D/'candidate-preparation.json')
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
files={n:sha(code/n) for n in base['manifest']['files']}
changes=[{'path':n,'before':base['manifest']['files'][n],'after':files[n],'reason':'Only indexed definition/reference SQL equivalence transformations and their exact dependency hash pins.'} for n in sorted(files) if base['manifest']['files'][n]!=files[n]]
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Supplemental synthetic test only; not served' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':changes,'base_code_root':base['manifest']['code_root'],'stage':str(code.relative_to(R)),'reason':'Selected MAIN103 bytes plus only two authorized SQL transformations; all source/profile/schema/search/data/budgets retained.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')}
integration={'schema_version':'local-release-integration-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'changes':changes,'candidate':binding,'rebase_receipt':ref};put(D/'integration.json',integration)
m=read(A/'실험/manifest.json');m['design']['release_rebase']=ref
m['design']['code_isolation']['candidates'] += [{**binding,'candidate_id':'sql-main-r2','arm_id':'optimized','experiment_id':m['experiment_id'],'run_ids':['run-002'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1073/audit_r2.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit_r2.py')}]
put(A/'실험/manifest.json',m)
frozen={str(p.relative_to(R)):sha(p) for p in (R/'06_TOOLS/EXPERIMENTS/adr_1073').glob('*.py')}
frozen.update({str(p.relative_to(R)):sha(p) for p in D.glob('*.json')})
frozen[str((C/'candidate.json').relative_to(R))]=sha(C/'candidate.json')
frozen.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
# Baseline functions and all selected release bytes remain immutable inputs.
frozen.update({str((R/base['manifest']['code_root']/n).relative_to(R)):h for n,h in base['manifest']['files'].items()})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen',len(files),'serving files;',len(changes),'changes; independent628case census, no model/corpus')
