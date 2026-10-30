import sys
sys.dont_write_bytecode=True
from pathlib import Path
import hashlib,json,gzip
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract';ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json

def read(p):
 p=Path(p)
 if p==DES/'freeze.json':p=sorted(DES.glob('execution-binding-*.json'))[-1] if list(DES.glob('execution-binding-*.json')) else sorted(DES.glob('freeze-rev-*.json'))[-1]
 if not p.exists() and p.with_suffix(p.suffix+'.gz').exists():p=p.with_suffix(p.suffix+'.gz')
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:v=json.load(f)
 if isinstance(v,dict) and set(v)=={'raw_json'}:return read(v['raw_json']['path'])
 return v

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def put(p,v):
 p=Path(p)
 if p==ADR/'실험/manifest.json' or '/scoped/snapshot/' in str(p):
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');return
 if p==DES/'freeze.json':p=DES/('freeze-'+v['candidate_revision']['revision_id']+'.json')
 if p.name in ('audit.json','response.json','investigation-state.json'):
  ref=write_raw_json(p.with_suffix('.json.gz'),v);write_summary(p,{'raw_json':ref})
 else:write_summary(p,v)
