"""Read-only adapter check; no RAG evaluation, queries, or external model calls."""
import json,sqlite3
from collections import Counter
from types import SimpleNamespace
from run_probe import R,A,read,sha,new,load
mods,_=load();active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);root=R/release['data_path'];manifest=read(root/'manifest.json');before=sha(root/'store.sqlite');assert before==manifest['store_sha256']
db=sqlite3.connect((root/'store.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
store=SimpleNamespace(db=db,manifest=manifest);dummy=SimpleNamespace(_unit_sources=lambda d,u:[],starts=lambda q,s:{})
m=mods['bound'].bind_structure(dummy,store);counts=Counter();errors=[]
for (d,u),n in m.units.items():
 counts['units']+=1;counts['stored_full_coordinate']+=bool(n.get('legal_coordinate'));counts['stored_scope_key']+=bool(n.get('coordinate_scope') and n.get('coordinate_key'))
 try:
  c=mods['bound'].stored_coordinate(m.units,d,u)
  if c:counts['coordinate_deserializable']+=1
  if c and not (n.get('coordinate_scope') and n.get('coordinate_key')):counts['coordinate_without_stored_scope_key']+=1
 except Exception as e:errors.append({'document_id':d,'unit_id':u,'error':str(e)})
db.close();assert sha(root/'store.sqlite')==before
new(A/'stored-contract.json',{'kind':'read-only storage adapter contract; not retrieval accuracy','active_release':active['release_id'],'generation_id':manifest['generation_id'],'store_sha256':before,'counts':dict(counts),'errors':errors,'passed':not errors,'model_calls':0,'external_transmission':False,'source_store_unchanged':True})
print(json.dumps({'counts':dict(counts),'errors':len(errors)},ensure_ascii=False))
