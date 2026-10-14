"""Restore this task's exact working edits only; refuse all later drift."""
from pathlib import Path
import argparse,json,hashlib,shutil,os
p=argparse.ArgumentParser();p.add_argument('--confirm-working-rollback',action='store_true');args=p.parse_args()
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0744-focused-rules-final-qualification'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=json.loads((A/'artifacts/working-install-receipt.json').read_text())['files']
for row in rows:
 assert sha(R/row['path'])==row['after'],'Later edit must be reviewed: '+row['path']
 if row['before']:assert sha(A/'artifacts/working-backup'/row['path'])==row['before']
if not args.confirm_working_rollback:
 print('Dry check passed; --confirm-working-rollback required to restore files; active MAIN is separate');raise SystemExit(0)
for row in rows:
 target=R/row['path']
 if row['before']:
  temp=target.with_name('.'+target.name+'.rollback');shutil.copy2(A/'artifacts/working-backup'/row['path'],temp);os.replace(temp,target)
 else:target.unlink()
print('Exact scoped working files restored; active MAIN pointer requires separate stable rollback')
