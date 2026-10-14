"""Restore only this task's working files after explicit MAIN pointer rollback."""
import argparse,hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration'
p=argparse.ArgumentParser();p.add_argument('--confirm-working-rollback',action='store_true');a=p.parse_args();assert a.confirm_working_rollback
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();plan=json.loads((A/'artifacts/working-install-plan.json').read_text());changes=plan['files'];backup=R/plan['backup']
docs_path=A/'artifacts/main-documentation-plan.json'
docs=json.loads(docs_path.read_text())['files'] if docs_path.exists() else []
for r in docs:
 h=sha(R/r['path']);assert h in (r['before'],r.get('after')), 'Concurrent documentation edit preserved: '+r['path']
for r in changes:
 p=R/r['path'];h=sha(p) if p.exists() else None
 if h!=r['before']:assert h==r['after'],'Concurrent edits preserved; manual review required: '+r['path']
for r in reversed(changes):
 p=R/r['path'];h=sha(p) if p.exists() else None
 if h==r['before']:continue
 if r['before'] is None:p.unlink()
 else:shutil.copy2(backup/r['path'],p)
for r in docs:
 if sha(R/r['path'])!=r['before']:shutil.copy2(R/r['backup'],R/r['path'])
print('Working files restored; source generations and runtime DBs preserved.')
