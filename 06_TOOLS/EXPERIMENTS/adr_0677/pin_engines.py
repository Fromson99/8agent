from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0677/integrated/snapshot'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(S/'00_SYSTEM/PIPELINE.json')
for e in m['engines'].values():
 p=S/e['manifest'];v=read(p)
 for f in v['files']:v['files'][f]=sha(S/f)
 put(p,v);e['sha256']=sha(p)
for e in m['contracts'].values():e['schema_sha256']=sha(S/e['schema_path'])
put(S/'00_SYSTEM/PIPELINE.json',m)
