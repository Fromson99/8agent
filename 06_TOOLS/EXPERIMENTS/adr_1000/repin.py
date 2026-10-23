from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 if 'files' in d:
  d['files']={n:sha(C/n) for n in d['files']};save(p,d)
p=C/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(C/e['manifest'])
save(p,d)
