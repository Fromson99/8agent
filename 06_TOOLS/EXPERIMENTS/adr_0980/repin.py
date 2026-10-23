from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if 'files' in v:
  for n in v['files']:v['files'][n]=sha(C/n)
  save(p,v)
def pins(v):
 if isinstance(v,dict):
  if v.get('manifest') and 'sha256' in v and (C/v['manifest']).is_file():v['sha256']=sha(C/v['manifest'])
  for x in v.values():pins(x)
 elif isinstance(v,list):
  for x in v:pins(x)
p=C/'00_SYSTEM/PIPELINE.json';v=read(p);pins(v);save(p,v)
