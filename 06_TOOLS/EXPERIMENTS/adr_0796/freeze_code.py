from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0796/selected';S=C/'snapshot';T=R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS';sys.path.insert(0,str(T));import adr_candidate as tool
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
extra=['02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/semantic_runtime/filename_versions.py','00_SYSTEM/FILENAME_EXCEPTIONS.json','02_BACKEND/lawrag/pipeline/search_selection.py','02_BACKEND/lawrag/pipeline/document_representations.py']
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' not in v:continue
 if '02_BACKEND/semantic_runtime/storage.py' in v['files']:
  for n in extra:v['files'][n]=sha(S/n)
 v['files']={n:sha(S/n) for n in v['files']};put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,v)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
tool.refresh(C)
