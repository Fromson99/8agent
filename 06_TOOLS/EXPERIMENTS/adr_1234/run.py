from pathlib import Path
import hashlib,json,os,runpy,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1234-gold-ontology-reference-repair';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json')
for p,h in f['files'].items():assert sha(R/p)==h,'FROZEN_FILE_CHANGED:'+p
assert sys.argv[1:] == ['gold-369']
os.environ.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1');sys.dont_write_bytecode=True
entry=R/read(D/'candidate.json')['entry'];sys.argv=[str(entry),'gold-369'];runpy.run_path(str(entry),run_name='__main__')
