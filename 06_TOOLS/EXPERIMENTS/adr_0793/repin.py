from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0793/connected/snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' not in v:continue
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in v['files']:v['files']['02_BACKEND/semantic_runtime/legal_agent/definition_entry.py']=sha(C/'02_BACKEND/semantic_runtime/legal_agent/definition_entry.py')
 v['files']={k:sha(C/k) for k in v['files']};put(p,v)
p=C/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
def profiles(obj):
 if isinstance(obj,dict):
  if obj.get('path','').startswith('00_SYSTEM/LEGAL_AGENT/') and 'sha256' in obj:obj['sha256']=sha(C/obj['path'])
  for child in obj.values():profiles(child)
 elif isinstance(obj,list):
  for child in obj:profiles(child)
profiles(v)
for e in v['engines'].values():e['sha256']=sha(C/e['manifest'])
put(p,v)
