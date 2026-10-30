from pathlib import Path
import json,hashlib,os,runpy,sys
R=Path('/home/jin/8-AGENT');D=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation/artifacts/design'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
f=json.loads((D/'freeze.json').read_text());action=sys.argv[1]
assert action in f['entries'],action
for p,h in f['files'].items():assert sha(R/p)==h,p
b=json.loads((D/'baseline.json').read_text());C=R/b['release']['code_root']
assert all(sha(C/n)==h for n,h in b['release']['files'].items())
# Another task may select a newer MAIN. This experiment stays on the exact
# 487-file MAIN120 snapshot, and never rewrites or follows the active pointer.
active=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
if sha(active)!=b['pointer_sha256']:
 observation=D.parent/'concurrent-main-change.json'
 value={'baseline_pointer_sha256':b['pointer_sha256'],'observed_pointer_sha256':sha(active),'observed_pointer':json.loads(active.read_text()),'experiment_code_root':str(C),'engine_files_verified':len(b['release']['files']),'action':'retain frozen MAIN120; no active pointer mutation'}
 if not observation.exists():observation.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
os.environ.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
sys.dont_write_bytecode=True;entry=R/f['entries'][action];sys.path.insert(0,str(entry.parent));sys.argv=[str(entry),*sys.argv[2:]];runpy.run_path(str(entry),run_name='__main__')
