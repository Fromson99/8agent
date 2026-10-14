from pathlib import Path
import json,tarfile,re,hashlib
R=Path(__file__).resolve().parents[3];P=R/'04_EXPERIMENTS/ADR/ADR-0711-compact-selection-source-input';A=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
pat=re.compile(rb'article:[0-9a-f]{24}');old=json.loads((P/'artifacts/design/excluded-source-ids.json').read_text());ids=set(old);files=[];failures=[]
for p in (P/'artifacts/run-001').rglob('*.json'):
 b=p.read_bytes();ids.update(x.decode() for x in pat.findall(b));files.append({'path':str(p.relative_to(R)),'sha256':hashlib.sha256(b).hexdigest()})
p=P/'artifacts/run-001/raw.tar.gz'
with tarfile.open(p) as tar:
 for m in tar:
  if m.isfile() and m.name.endswith(('.json','.jsonl','.log')):
   b=tar.extractfile(m).read();ids.update(x.decode() for x in pat.findall(b))
files.append({'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(D/'excluded-source-ids.json').write_text(json.dumps(sorted(ids))+'\n')
(D/'exposure-scan.json').write_text(json.dumps({'inherited':len(old),'total_excluded':len(ids),'files':files,'failures':failures,'scope':'Inherited full scan through ADR0710 plus every0711 request/result/raw JSON; SQL durable views already represented in provider inputs; excludes known roots and all offered candidates, not a pretraining claim.'},ensure_ascii=False,indent=2)+'\n')
print('Excluded',len(ids),'source IDs')
