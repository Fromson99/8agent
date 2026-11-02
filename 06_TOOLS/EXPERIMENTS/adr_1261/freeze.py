from pathlib import Path
import json,hashlib,sys,ast
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_1261/checkpoint';S=C/'snapshot';read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as z:return hashlib.file_digest(z,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'baseline.json');changes={n:sha(S/n) for n in ['02_BACKEND/semantic_runtime/oracle_agent_records.py','02_BACKEND/semantic_runtime/oracle_progress_body.py']}
for n in changes:ast.parse((S/n).read_text())
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if 'files' not in v or not set(changes)&set(v['files']):continue
 before=sha(p);v['files'].update(changes);put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for old,new in hashes.items():s=s.replace(old,new)
p.write_text(s)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((R/f['frozen_path']).relative_to(code)):f['snapshot_sha256'] for f in v['files']};pin={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']};put(D/'freeze.json',{'code_root':str(code.relative_to(R)),'files':files,'candidate_revision':pin,'products':changes,'criteria_sha256':sha(D/'criteria.json')})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='checkpoint',experiment_id=m['experiment_id'],arm_id='compact',run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1261/check.py',runner_sha256=sha(R/'06_TOOLS/EXPERIMENTS/adr_1261/check.py'))]);m['design']['criteria_freeze_evidence']={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')};put(A/'실험/manifest.json',m);print('Frozen',v['revision_id'],len(files),'serving files;2 product modules')
