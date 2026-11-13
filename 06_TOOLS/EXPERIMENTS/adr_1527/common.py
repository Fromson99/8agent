from pathlib import Path
import hashlib,json,sys,gzip,os
ROOT=Path('/home/jin/8-AGENT')
TOOLS=Path(__file__).resolve().parent
TARGET=os.environ.get('ADR_TARGET',TOOLS.name.split('_')[1])
_found=sorted((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-'+TARGET+'-*'))
assert len(_found)==1,('ADR folder for target',TARGET,_found)
ADR=_found[0];ART=ADR/'artifacts';DES=ART/'design'
sys.dont_write_bytecode=True
def read(p):
 p=Path(p)
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as stream:v=json.load(stream)
 if isinstance(v,dict) and set(v)=={'raw_json'}:return read(v['raw_json']['path'])
 return v
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p==ADR/'실험/manifest.json':
  p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');return
 # Prior observer revisions stay immutable; the pointer is replaced atomically.
 h=hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 versions=p.parent/'.observer-versions';versions.mkdir(exist_ok=True)
 dest=versions/(p.stem+'-'+h+'.json')
 if not dest.exists():
  try:write_summary(dest,v)
  except ValueError:
   ref=write_raw_json(dest.with_suffix('.json.gz'),v);write_summary(dest,{'raw_json':ref})
 if p.exists():
  old=versions/(p.stem+'-bytes-'+sha(p)+'.json')
  if not old.exists():os.link(p,old)
 temp=p.with_name('.'+p.name+'.pointer')
 if temp.exists():
  assert p.exists() and os.path.samefile(temp,p);temp.unlink()
 os.link(dest,temp);os.replace(temp,p)
 if temp.exists():
  assert os.path.samefile(temp,p);temp.unlink()
def gz(p,v):
 ref=write_raw_json(p,v);put(Path(str(p)+'.ref.json'),{'raw_json':ref})
