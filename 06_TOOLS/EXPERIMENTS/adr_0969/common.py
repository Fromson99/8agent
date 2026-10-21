from pathlib import Path
import hashlib,json,gzip
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0969-dense-rerank-cm-probe'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
TARGET='02_BACKEND/semantic_runtime/dense_rerank_probe.py'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def gz(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,'wt',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,separators=(',',':'))
def readgz(p):
    with gzip.open(p,'rt',encoding='utf8') as f:return json.load(f)
