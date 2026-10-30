from pathlib import Path
import hashlib,json,os,runpy,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
f=json.loads((A/'artifacts/design/freeze.json').read_text())
for p,h in f['files'].items():assert sha(R/p)==h,p
os.environ.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
sys.dont_write_bytecode=True
entry=R/f['entry'];runpy.run_path(str(entry),run_name='__main__')
