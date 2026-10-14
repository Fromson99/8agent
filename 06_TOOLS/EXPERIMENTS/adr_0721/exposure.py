from pathlib import Path
import re,json,tarfile,hashlib
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0721-request-repair-final-qualification/artifacts/design';D.mkdir(parents=True,exist_ok=True)
old=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/artifacts/design/excluded-source-ids.json'
ids=set(json.loads(old.read_text()));pat=re.compile(rb'article:[0-9a-f]{24}');files=[];fail=[]
for n in range(712,721):
 matches=list((R/'04_EXPERIMENTS/ADR').glob(f'ADR-{n:04}-*'))
 if len(matches)!=1:fail.append(str(n));continue
 for p in matches[0].joinpath('artifacts').rglob('*'):
  if not p.is_file() or not (p.suffix in ('.json','.jsonl') or p.name.endswith('.tar.gz')):continue
  if 'working-backup' in p.parts:continue
  h=hashlib.sha256()
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  files.append({'path':str(p.relative_to(R)),'sha256':h.hexdigest()})
  if p.name.endswith('.tar.gz'):
   with tarfile.open(p) as t:
    for m in t:
     if m.isfile() and m.name.endswith(('.json','.jsonl','.log')):
      stream=t.extractfile(m);tail=b''
      for chunk in iter(lambda:stream.read(1024*1024),b''):
       data=tail+chunk;ids.update(x.decode() for x in pat.findall(data));tail=data[-32:]
  else:
   with p.open('rb') as f:
    tail=b''
    for chunk in iter(lambda:f.read(1024*1024),b''):
     data=tail+chunk;ids.update(x.decode() for x in pat.findall(data));tail=data[-32:]
(D/'excluded-source-ids.json').write_text(json.dumps(sorted(ids))+'\n')
(D/'exposure-scan.json').write_text(json.dumps({'inherited':str(old.relative_to(R)),'inherited_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'files':files,'excluded':len(ids),'failures':fail,'scope':'Inherited full scan through0711 plus0712-0720 exact product payloads and diagnostics; candidate/read roots excluded. Not an LLM pretraining claim.'},ensure_ascii=False,indent=2)+'\n')
print('excluded',len(ids),'files',len(files),'failures',fail)
