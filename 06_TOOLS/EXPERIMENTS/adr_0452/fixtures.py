import sqlite3,json,hashlib
from types import SimpleNamespace
from runtime import read,sha

def build(folder):
 rows=read(folder/'sources.json');sources={s['id']:s for s in rows};docs=read(folder/'documents.json');documents={d['id']:d['name'] for d in docs};terms={t['id']:t for t in read(folder/'terms.json')};edges={t:[] for t in terms}
 for e in read(folder/'edges.json'):edges[e['source']].append(e);edges[e['target']].append(e)
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.executescript('CREATE TABLE document(document_id,name,json);CREATE TABLE source_unit(document_id,unit_id,parent_id,json);CREATE TABLE occurrence(term_id,source_id);CREATE TABLE reference(id,json);CREATE TABLE reference_end(source_id,reference_id);')
 db.executemany('INSERT INTO document VALUES (?,?,?)',[(d['id'],d['name'],json.dumps({'document_category':d['document_category']})) for d in docs]);units={}
 for did,nodes in read(folder/'structure-units.json').items():
  for n in nodes:
   units[(did,str(n['id']))]={**n,'parent':str(n['parent']) if n['parent'] is not None else None};db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,str(n['id']),n['parent'],json.dumps(n,ensure_ascii=False)))
 db.executemany('INSERT INTO occurrence VALUES (?,?)',[(t,s['id']) for s in rows for t in s['terms']])
 for ref in read(folder/'references.json'):
  db.execute('INSERT INTO reference VALUES (?,?)',(ref['id'],json.dumps(ref,ensure_ascii=False)));db.executemany('INSERT INTO reference_end VALUES (?,?)',[(s,ref['id']) for s in [ref['source_id']]+ref['target_source_ids']])
 def validate(scope):
  if not scope or set(scope)-documents.keys():raise ValueError('invalid authorized scope')
  return sorted(set(scope))
 tools=SimpleNamespace(terms=terms,edges=edges,db=db,sources=sources,validate_scope=validate)
 def starts(q,scope):
  span=lambda text:[{'text':text,'start':q.index(text),'end':q.index(text)+len(text)}]
  return {'documents':[{'id':d,'name':n,'question_spans':span(n)} for d,n in documents.items() if d in scope and n in q],'terms':[{'id':t,'question_spans':span(v['label'])} for t,v in terms.items() if v['label'] in q],'structures':[{'id':'structure:'+d+':'+u,'document_id':d,'family':n['family'],'kind':'LOCATOR','question_spans':span(n['surface'])} for (d,u),n in units.items() if d in scope and n['surface'] in q]}
 def unit_sources(d,u):
  while u is not None:
   ids=[s['id'] for s in rows if s['document_id']==d and str(s['unit_id'])==u]
   if ids:return ids
   u=units.get((d,u),{}).get('parent')
  return []
 m=SimpleNamespace(tools=tools,sources=sources,documents=documents,units=units,starts=starts,_unit_sources=unit_sources)
 g=SimpleNamespace(connections=SimpleNamespace(_definitions=lambda source,node,end:[{'text':terms[node]['label']+'의 모의 용어 정의. 실제 조건은 연결된 원문에서 확인한다.','id':'definition:'+node}]))
 hashes={p.name:sha(p) for p in folder.glob('*.json') if p.name!='product-cases.json'};manifest={'generation_id':'synthetic-449-v1','store_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),'data_status':'EXAMPLE','scope':{'document_version_ids':sorted(documents)}}
 return SimpleNamespace(db=db,manifest=manifest),m,g
