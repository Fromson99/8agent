from pathlib import Path
import json,sys,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1165-vector-navigation-connected';C=R/'02_BACKEND/lawrag/research/candidates/adr_1165/integrated';S=C/'snapshot';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
known={f['target_path'] for f in read(C/'candidate.json')['files']}
for p in S.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts and str(p.relative_to(S)) not in known:ac.register_file(C,str(p.relative_to(S)),upstream_state='absent')
new=['02_BACKEND/semantic_runtime/'+n+'.py' for n in ('initial_vector','vector_publish','vector_navigation','oracle_silver_reads')]+['00_SYSTEM/ORACLE/physical_mapping.yaml']
pipe=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipe['engines'].values():
 p=S/ref['manifest'];e=read(p)
 for n in new:e['files'][n]=sha(S/n)
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipe)
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');v=c['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((R/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']};binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((T/'check.py').relative_to(R)),runner_sha256=sha(T/'check.py'))]);put(A/'실험/manifest.json',m);put(A/'artifacts/design/freeze.json',{'code_root':str(code.relative_to(R)),'files':files,'binding':binding});print(v['revision_id'],len(files))
