from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0856/assembled';S=C/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
new='02_BACKEND/semantic_runtime/legal_agent/minimal_output.py'
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
    v=json.loads(p.read_text());files=v.get('files')
    if not isinstance(files,dict):continue
    if any(n in files for n in ('02_BACKEND/semantic_runtime/legal_agent/gateway.py',
        '02_BACKEND/semantic_runtime/ad_model.py','02_BACKEND/semantic_runtime/genos_backend.py')):
        files[new]=sha(S/new)
    if '02_BACKEND/semantic_runtime/genos_backend.py' in files:
        files['02_BACKEND/lawrag/core/llm.py']=sha(S/'02_BACKEND/lawrag/core/llm.py')
    for n in files:
        if (S/n).exists():files[n]=sha(S/n)
    put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,v)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
print('Candidate syntax and engine pins ready')
