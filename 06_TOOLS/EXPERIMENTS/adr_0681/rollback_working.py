"""Restore only this task's saved working edits, refusing later file changes."""
from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing'
assert '--confirm-working-rollback' in sys.argv
m=json.loads((A/'artifacts/working-install-receipt.json').read_text())
docs=A/'artifacts/main-documentation-receipt.json'
if docs.exists():m['files'].extend(json.loads(docs.read_text())['files'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for row in m['files']:assert sha(R/row['path'])==row['after'],'Later working change: '+row['path']
for row in reversed(m['files']):
 p=R/row['path']
 if row['before'] is None:p.unlink()
 else:
  backup=R/row['backup'] if 'backup' in row else A/'artifacts/working-backup'/row['path']
  assert sha(backup)==row['before'];shutil.copy2(backup,p)
print('Restored only ADR0681 files; stored data and completed releases preserved')
