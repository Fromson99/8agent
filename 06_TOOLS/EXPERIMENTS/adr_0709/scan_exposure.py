from pathlib import Path
import re,json,gzip,tarfile,hashlib
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0709-grounded-entry-main-qualification/artifacts/design';D.mkdir(parents=True,exist_ok=True)
prior=R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout/artifacts/design/excluded-source-ids.json';excluded=set(json.loads(prior.read_text()));scanned=[];failures=[]
def absorb(data):excluded.update(x.decode() for x in re.findall(rb'article:[a-f0-9]{16,64}',data))
for a in sorted((R/'04_EXPERIMENTS/ADR').glob('ADR-*')):
 try:n=int(a.name.split('-')[1])
 except ValueError:continue
 if not 703<=n<709:continue
 for p in sorted((a/'artifacts').rglob('*')):
  if not p.is_file() or any(t in p.parts for t in ('fixture-code','prepared-generations','pre-review-code')):continue
  try:
   if p.name.endswith(('.tar.gz','.tgz')):
    with tarfile.open(p,'r:gz') as t:
     for member in t:
      if member.isfile() and member.name.endswith(('.json','.jsonl','.txt','.log')):absorb(t.extractfile(member).read())
   elif p.name.endswith(('.json.gz','.jsonl.gz','.log.gz')):
    with gzip.open(p,'rb') as f:absorb(f.read())
   elif p.suffix in ('.json','.jsonl','.md','.txt','.log'):absorb(p.read_bytes())
   else:continue
   scanned.append(str(p.relative_to(R)))
  except Exception as e:failures.append({'path':str(p.relative_to(R)),'error':str(e)})
(D/'excluded-source-ids.json').write_text(json.dumps(sorted(excluded))+'\n')
(D/'exposure-scan.json').write_text(json.dumps({'inherited_path':str(prior.relative_to(R)),'inherited_sha256':hashlib.sha256(prior.read_bytes()).hexdigest(),'scan_rule':'All article identifiers in prior0703-0708 design, result, raw input/output and compressed records; inherited full exclusion chain through0702. Does not assert absence from model pretraining.','scanned':scanned,'failures':failures,'excluded_count':len(excluded)},ensure_ascii=False,indent=2)+'\n')
print('exclusions',len(excluded),'files',len(scanned),'failures',len(failures))
for sid in ['article:a8d55fcd2801e19913c03efc','article:29b0c976480bcdb058ac8d9e','article:3cdb5a4dfc8192461e938876']:print(sid,'excluded',sid in excluded)
