from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration'
ART=ADR/'artifacts';DES=ART/'design';OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-rag-ontology-console-integration'
GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}

RELEASE='ontology-console-20261103-r1'
