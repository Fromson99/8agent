"""Restore only this installation's files, refusing to overwrite later changes."""
from pathlib import Path
import argparse,json,hashlib,shutil,subprocess
p=argparse.ArgumentParser();p.add_argument('--confirm-working-rollback',action='store_true');args=p.parse_args()
if not args.confirm_working_rollback:raise SystemExit('Explicit --confirm-working-rollback is required')
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout'
receipt=json.loads((A/'artifacts/working-install-receipt.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[r for r in receipt['files'] if r['kind'] in ('runtime','test')]
for row in rows:
 assert sha(R/row['path'])==row['after'],'Later edit must be reviewed: '+row['path']
 if row['before']:assert sha(A/'artifacts/working-backup'/row['path'])==row['before']
for row in rows:
 target=R/row['path']
 if row['before']:shutil.copy2(A/'artifacts/working-backup'/row['path'],target)
 else:target.unlink()
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','rehash-engines','--apply'],cwd=R,check=True)
print('Scoped working files restored; active MAIN pointer is a separate rollback')
