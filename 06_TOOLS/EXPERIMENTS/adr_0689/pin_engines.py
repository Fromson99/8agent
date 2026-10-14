"""Recalculate actual candidate dependency pins; never bypass verification."""
import json, hashlib, sys
from pathlib import Path
R=Path(__file__).resolve().parents[3]
S=Path(sys.argv[1]) if len(sys.argv)>1 else R/'02_BACKEND/lawrag/research/candidates/adr_0689/repaired/snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
config=read(S/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
 p=S/entry['manifest'];engine=read(p)
 for path in engine['files']:engine['files'][path]=sha(S/path)
 put(p,engine);entry['sha256']=sha(p)
for c in config['contracts'].values():c['schema_sha256']=sha(S/c['schema_path'])
put(S/'00_SYSTEM/PIPELINE.json',config)
print('Verified dependency files and repinned candidate engines')
