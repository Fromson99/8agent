from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0817/observed'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
for p in (R/'06_TOOLS/EXPERIMENTS/adr_0817').glob('*.py'):compile(p.read_text(),str(p),'exec')
for op in ('refresh','freeze','validate'):
    subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py',op,str(C)],check=True)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];snapshot=C/'revisions'/rev['revision_id']/'snapshot'
base=read(D/'baseline.json');release=base['manifest'];active=R/release['code_root']
assert all(sha(snapshot/n)==h==sha(active/n) for n,h in release['files'].items())
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
         'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
full={**binding,'candidate_id':'observed','arm_id':'observed','experiment_id':'ADR-0817-experiment-v1','run_ids':['run-001'],
      'runner_path':'06_TOOLS/EXPERIMENTS/adr_0817/live.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0817/live.py')}
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='isolated_candidate',reason='Exact selected338-file snapshot archived; actual active-pointer service executes identical selected release bytes. No product changes.',candidates=[full]);put(A/'실험/manifest.json',m)
paths=list((R/'06_TOOLS/EXPERIMENTS/adr_0817').glob('*.py'))+list(D.glob('*.json'))
paths += [C/'candidate.json',R/'service.py',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/base['pointer']['manifest_path'],R/release['data_path']/'manifest.json']
paths += list((R/'service').glob('*.py'))
paths += [active/n for n in release['files']]+[snapshot/n for n in release['files']]
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':release['code_root'],'candidate':binding,
                    'files':{str(p.relative_to(R)):sha(p) for p in paths},'serving_files':release['files']})
print('Frozen: exact MAIN76, four questions, actual-service runner, no model calls yet')
