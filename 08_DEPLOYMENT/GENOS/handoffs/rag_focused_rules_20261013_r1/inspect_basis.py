import importlib.util,json,gzip,hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];PRIOR=OUT.with_name('rag_progress_graph_20261008_r5')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=load('r5build',PRIOR/'build_delivery.py');cat,bases,cm=b.source_material()
a=load('r5apply',PRIOR/'apply_display.py');spec=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
print('bases',len(bases),flush=True)
new=ROOT/'08_DEPLOYMENT/RELEASES/focused-rules-20261013-r1/code'
base=ROOT/'08_DEPLOYMENT/RELEASES/session-runtime-v6-20261007-r1/code'
for p in (new/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py'):
 n=p.relative_to(new).as_posix();old=base/n
 if not old.exists() or old.read_bytes()!=p.read_bytes():
  hashes={v['pins'].get(n) for v in bases.values()};present=[cat[h] for h in hashes if h]
  print(p.name,'variants',len(hashes),'newequals',sum(x==p.read_bytes() for x in present),'baseequals',sum(old.exists() and x==old.read_bytes() for x in present))
