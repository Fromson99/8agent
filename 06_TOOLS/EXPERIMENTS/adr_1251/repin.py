from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_1251/generalized-isolated/snapshot';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();mapping={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text());before=sha(p);changed=False
 for n,h in v.get('files',{}).items():
  if (S/n).is_file() and sha(S/n)!=h:v['files'][n]=sha(S/n);changed=True
 if changed:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');mapping[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for old,new in mapping.items():s=s.replace(old,new)
p.write_text(s);print('repinned',len(mapping))
