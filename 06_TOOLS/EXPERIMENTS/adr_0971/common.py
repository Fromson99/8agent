from pathlib import Path
import sys, json, hashlib, gzip
sys.path.insert(0, str(Path.cwd()/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
ROOT=load_layout(Path.cwd()).root
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0971-fulltext-vector70'
ART=ADR/'artifacts'; DES=ART/'design'; RUN=ART/'run-001'
TARGET='02_BACKEND/semantic_runtime/fulltext_vector_probe.py'
def read(p): return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def gz(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,'wt',encoding='utf8') as f: json.dump(v,f,ensure_ascii=False)
def readgz(p):
    with gzip.open(p,'rt',encoding='utf8') as f:return json.load(f)
