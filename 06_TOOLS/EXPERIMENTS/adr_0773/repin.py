from pathlib import Path
import json,hashlib
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication/snapshot';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=S/'00_SYSTEM/PIPELINE.json';c=json.loads(p.read_text())
for entry in c['engines'].values():
 ep=S/entry['manifest'];e=json.loads(ep.read_text());e['files']={n:sha(S/n) for n in e['files']};ep.write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(ep)
p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
