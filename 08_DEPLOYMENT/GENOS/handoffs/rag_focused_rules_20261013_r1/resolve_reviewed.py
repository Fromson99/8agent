"""Reviewed conflict choices; keep field cache implementation byte-for-byte."""
import ast,re,json
from pathlib import Path
import build_delivery as b
cat,states,_=b.source_material();out=b.OUT/'reviewed';out.mkdir(exist_ok=True)
records=[]
for p in (b.OUT/'merge-review').glob('*.txt'):
 name,pin,_=p.name.rsplit('.',2) if False else ('','','')
 # filename = module.py.first12sha.txt
 module,short=p.name[:-4].rsplit('.',1);n='02_BACKEND/semantic_runtime/legal_agent/'+module
 hashes={s['pins'].get(n) for s in states};h=next(h for h in hashes if h and h.startswith(short));field=cat[h]
 pattern=r'^<<<<<<< .*?\n(.*?)^\|\|\|\|\|\|\| .*?\n(.*?)^=======\n(.*?)^>>>>>>> .*?\n'
 text=p.read_text();choices=[]
 def choose(m):
  choices.append({'field_sha256':b.sha(m[1].encode()),'base_sha256':b.sha(m[2].encode()),'selected_sha256':b.sha(m[3].encode()),'reason':'MAIN53 contains existing field instrumentation/CM path plus RAG change; cache restored separately'})
  return m[3]
 result=re.sub(pattern,choose,text,flags=re.M|re.S)
 if module=='law_candidates.py':
  def function(raw,name):
   lines=raw.decode().splitlines(keepends=True);node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name==name);return node,''.join(lines[node.lineno-1:node.end_lineno])
  oldtree=ast.parse(field);tree=ast.parse(result)
  # Existing helper name is _allowed; retain cache, scope and latency exactly.
  names=[x.name for x in oldtree.body if isinstance(x,ast.FunctionDef) and 'allowed' in x.name]
  for name in names:
   oldnode,original=function(field,name);node,current=function(result.encode(),name)
   result=result.replace(current,original,1)
  if b'from ..runtime_cache import CACHE' not in field:result=result.replace('from ..runtime_cache import CACHE\n','')
 ast.parse(result,feature_version=(3,10));dest=out/(module+'.'+h+'.py');dest.write_text(result)
 records.append({'path':n,'before_sha256':h,'after_sha256':b.sha(result.encode()),'conflicts':choices,'field_cache_preserved':module=='law_candidates.py'})
(b.OUT/'REVIEWED_MERGES.json').write_bytes(b.encoded(records))
print('reviewed',len(records))
