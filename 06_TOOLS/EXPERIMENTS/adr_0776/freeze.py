"""Freeze development changes; never changes selected data or MAIN."""
from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0776/recovery'
S=C/'snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pipeline=S/'00_SYSTEM/PIPELINE.json';p=json.loads(pipeline.read_text())
for ref in p['engines'].values():
    path=S/ref['manifest'];m=json.loads(path.read_text())
    for name in m['files']:m['files'][name]=sha(S/name)
    if any(name.startswith('02_BACKEND/semantic_runtime/') for name in m['files']):
        name='02_BACKEND/semantic_runtime/legal_agent/output_contract.py'
        m['files'][name]=sha(S/name)
    m['files']=dict(sorted(m['files'].items()));save(path,m);ref['sha256']=sha(path)
save(pipeline,p)
run=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),
    'adr_candidate.py','freeze',str(C)],cwd=R,capture_output=True,text=True)
if run.returncode:raise RuntimeError(run.stderr[-2000:]+run.stdout[-2000:])
v=json.loads((C/'candidate.json').read_text());rev=v['revisions'][-1]
path=R/v['adr_path']/'실험/manifest.json';m=json.loads(path.read_text())
ref=m['design']['code_isolation']['candidates'][0]
ref.update(manifest_sha256=sha(C/'candidate.json'),revision_id=rev['revision_id'],
    revision_sha256=rev['revision_sha256'],runner_sha256=sha(R/ref['runner_path']))
save(path,m)
print(json.dumps({k:rev[k] for k in ('revision_id','revision_sha256')}))
