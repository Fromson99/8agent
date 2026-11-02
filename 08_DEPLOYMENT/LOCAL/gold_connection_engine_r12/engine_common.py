"""Gold adapter helpers using the engine verified by the local connector."""
from pathlib import Path
import json,hashlib,os,sys,time,shutil,sqlite3
R=Path(REPOSITORY_ROOT);A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(Path(p).read_text())
def journal_allowed(name,root):
 from urllib.parse import urlsplit,unquote
 if name==':memory:':return True
 if name.startswith('file:'):
  parsed=urlsplit(name)
  if parsed.netloc not in ('','localhost'):return False
  path=Path(unquote(parsed.path))
 else:path=Path(name)
 return path.resolve().is_relative_to(Path(root).resolve())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n');os.replace(tmp,p)
B=ENGINE_BINDING;C=R/B['engine_root'];DATA=R/B['data_path']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.oracle_dp_io import canonical,digest
from gold_connection import GoldConfig,READ_COLUMNS,GoldError,LocalReadTransport,rewrite_reads,ReadNames
def cfg():return GoldConfig.load(D/'config_b03.json',R)
def docs():return sorted(x['document_id'] for x in read(D/'documents.json')['documents'])
def guard():
 mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
 status={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmRSS:','VmSwap:'))}
 free=min(shutil.disk_usage(R).free,shutil.disk_usage('/mnt/c').free)
 if free<80*1024**3 or mem['MemAvailable']<3*1024**3 or status['VmRSS']>5*1024**3 or status.get('VmSwap',0)>128*1024**2:raise RuntimeError('RESOURCE_GUARD')
 return dict(mem,**status,free_disk=free)
def connect(writer=False):
 import oracledb
 oracledb.defaults.fetch_lobs=False
 p=Path.home()/'.local/state/8-agent/gold-r12-1208'/('connection.json' if writer else 'readonly-connection.json')
 assert not p.stat().st_mode&0o077
 c=oracledb.connect(**read(p));c.call_timeout=60000;return c
def ro(p):
 c=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA cache_size=-16384');c.execute('PRAGMA temp_store=FILE');return c
def publisher_imports():
 import lawrag,lawrag.pipeline
 lawrag.__path__.append(str(R/'02_BACKEND/lawrag'));lawrag.pipeline.__path__.append(str(R/'02_BACKEND/lawrag/pipeline'))
 from lawrag.pipeline import oracle_query_publish as pub,oracle_query_navigation_publish as nav
 return pub,nav
