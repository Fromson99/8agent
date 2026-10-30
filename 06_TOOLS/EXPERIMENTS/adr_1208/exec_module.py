from pathlib import Path
import sys,json,hashlib,runpy,os
R=Path('/home/jin/8-AGENT');D=R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector/artifacts/design'
def sha(p):
    with p.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
name=sys.argv[1]
if name not in ('gold_capacity','gold_vectors','gold_check','gold_api','gold_vector_check','gold_bulk_indexes','gold_readonly'):raise ValueError('unknown isolated entry')
f=json.loads((D/'freeze.json').read_text())
for p,h in f['files'].items():
    if sha(R/p)!=h:raise RuntimeError('FROZEN_INPUT_CHANGED: '+p)
c=json.loads((R/f['manifest_path']).read_text());rev=next(x for x in c['revisions'] if x['revision_id']==f['revision_id'])
for row in rev['files']:
    if sha(R/row['frozen_path'])!=row['snapshot_sha256']:raise RuntimeError('FROZEN_CANDIDATE_CHANGED')
entry=R/f['code_root']/('08_DEPLOYMENT/LOCAL/gold_connection_r12/'+name+'.py')
sys.path.insert(0,str(entry.parent));sys.dont_write_bytecode=True;os.environ['GOLD_WORKSPACE']=str(R)
sys.argv=[str(entry),*sys.argv[2:]];runpy.run_path(str(entry),run_name='__main__')
