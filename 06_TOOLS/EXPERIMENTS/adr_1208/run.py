"""Execute only the latest explicitly frozen isolated R12 lab revision."""
from pathlib import Path
import sys,json,hashlib,runpy,os
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector';D=A/'artifacts/design'
def sha(p):
    with p.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
f=json.loads((D/'freeze.json').read_text())
for p,h in f['files'].items():
    if sha(R/p)!=h:raise RuntimeError('FROZEN_INPUT_CHANGED: '+p)
c=R/f['manifest_path'];m=json.loads(c.read_text());revision=next(x for x in m['revisions'] if x['revision_id']==f['revision_id'])
for row in revision['files']:
    if sha(R/row['frozen_path'])!=row['snapshot_sha256']:raise RuntimeError('FROZEN_CANDIDATE_CHANGED')
entry=R/f['code_root']/'08_DEPLOYMENT/LOCAL/gold_connection_r12/gold_lab.py'
sys.path.insert(0,str(entry.parent));sys.dont_write_bytecode=True;os.environ['GOLD_WORKSPACE']=str(R)
sys.argv=[str(entry),*sys.argv[1:]];runpy.run_path(str(entry),run_name='__main__')
