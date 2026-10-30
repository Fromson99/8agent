"""Freeze contract-development repairs; never overwrite prior revisions/logs."""
from pathlib import Path
import sys,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding';C=R/'02_BACKEND/lawrag/research/candidates/adr_1086/compact-r1';S=C/'snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=S/'02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py';s=p.read_text();old="acquired.update((e['evidence_id'], e) for e in projected)";assert old in s;s=s.replace(old,"acquired.update((e['evidence_id'], {**e, 'text': '\\n'.join(span['text'] for span in e['spans'])}) for e in projected)");p.write_text(s)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text());rel='02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py'
for ref in v['engines'].values():
 ep=S/ref['manifest'];e=json.loads(ep.read_text())
 if rel in e['files']:e['files'][rel]=sha(S/rel);put(ep,e);ref['sha256']=sha(ep)
put(p,v)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac;ac.freeze(C)
f=json.loads((A/'artifacts/design/freeze.json').read_text());put(A/'artifacts/design/freeze-rev002.json',f)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';f.update(code_root=str(code.relative_to(R)),note='Contract repair: newly projected assessment evidence uses the repository exact newline join for text; no extra SQL. Earlier API failure and revisions preserved. No live/model effect experiment yet.')
f['binding'].update(manifest_sha256=sha(C/'candidate.json'),revision_id=rev['revision_id'],revision_sha256=rev['revision_sha256']);f['files']={n:sha(code/n) for n in f['files']};put(A/'artifacts/design/freeze.json',f)
m=json.loads((A/'실험/manifest.json').read_text());m['design']['code_isolation']['candidates'][0].update(f['binding'],runner_sha256=sha(R/'06_TOOLS/EXPERIMENTS/adr_1086/contracts.py'));put(A/'실험/manifest.json',m)
