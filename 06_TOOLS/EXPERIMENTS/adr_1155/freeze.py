from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1155-investigation-focus-offline';C=R/'02_BACKEND/lawrag/research/candidates/adr_1155/focused-r1';S=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
new='02_BACKEND/semantic_runtime/legal_agent/investigation_focus.py'
if not any(r['target_path']==new for r in read(C/'candidate.json')['files']):ac.register_file(C,new,upstream_state='absent')
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 if 'files' in d:
  for name in d['files']:d['files'][name]=sha(S/name)
  if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in d['files']:d['files'][new]=sha(S/new)
  put(p,d)
p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,d)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
ac.freeze(C);errors=ac.validate(C);assert not errors,errors
c=read(C/'candidate.json');v=c['revisions'][-1];root=C/'revisions'/v['revision_id']/'snapshot'
files={str((R/r['frozen_path']).relative_to(root)):r['snapshot_sha256'] for r in v['files']}
put(A/'artifacts/design/freeze.json',{'code_root':str(root.relative_to(R)),'files':files,'revision':v['revision_id'],'candidate_sha256':sha(C/'candidate.json')})
print(root)
