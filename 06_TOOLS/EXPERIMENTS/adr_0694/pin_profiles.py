from pathlib import Path
import json,hashlib,sys
s=Path(sys.argv[1]);p=s/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text());rows=[]
def walk(x):
 if isinstance(x,dict):
  if set(x)>={'path','sha256'} and (s/x['path']).is_file():
   h=hashlib.sha256((s/x['path']).read_bytes()).hexdigest()
   if h!=x['sha256']:rows.append(x['path']);x['sha256']=h
  for val in x.values():walk(val)
 elif isinstance(x,list):
  for val in x:walk(val)
walk(v['profiles']);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');print('Rebound actual profiles:',rows)
