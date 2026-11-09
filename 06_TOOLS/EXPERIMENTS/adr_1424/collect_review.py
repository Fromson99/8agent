"""Offline CM review collection; reference answers never enter product input.

Registry target document IDs come from an older generation. Each required target is
matched on the current store by law name + article coordinate; the review records
whether that article was acquired and whether a cited claim source covers it, and flags
targets whose registry document ID is not the current document (version may differ).
"""
from common import *
import sqlite3,argparse,re
from collections import defaultdict
SECTION_MARK='에서 절 제목의 핵심 표현을 함께 쓰는 조문 자동 확보'
rel=read(DES/'baseline.json')['release'];db=sqlite3.connect((ROOT/rel['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
names={d:n.split(' > ')[-1] for d,n in db.execute('SELECT document_id,name FROM document')}
_units={}
def units(did):
 if did not in _units:
  rows={}
  for uid,parent,raw in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
   v=json.loads(raw);rows[str(uid)]={'parent':None if parent is None else str(parent),'surface':v.get('surface') or '','family':v.get('family'),'span':v.get('span')}
  _units[did]=rows
 return _units[did]
def _in_addenda(did,uid):
 us=units(did);u=us[uid]['parent'];seen=set()
 while u in us and u not in seen:
  seen.add(u)
  if us[u]['surface'].replace(' ','').startswith('부칙'):return True
  u=us[u]['parent']
 return False
def article_root(did,label,scope='body'):
 """Same article number exists in the body and in 부칙; honour the registry coordinate scope."""
 hits=[uid for uid,u in units(did).items() if u['family']=='kr_article' and u['surface'].replace(' ','')==label.replace(' ','')]
 want_addenda=str(scope or 'body')!='body'
 hits=[h for h in hits if _in_addenda(did,h)==want_addenda] or hits
 return sorted(hits,key=lambda h:int(h) if h.isdigit() else 0)[0] if hits else None
def root_of(did,uid):
 seen=set();u=str(uid);us=units(did)
 while u in us and u not in seen:
  seen.add(u)
  if us[u]['family']=='kr_article':return u
  u=us[u]['parent']
 return None
_blocks={}
def block_root(did,bid):
 if did not in _blocks:
  _blocks[did]={str(b):str(u) for b,u in db.execute('SELECT block_id,unit_id FROM source_block WHERE document_id=?',(did,))}
 u=_blocks[did].get(str(bid))
 return root_of(did,u) if u else None

def collect():
 grades={g['id']:g for g in read(DES/'grading-only.json')}
 audit={a['case_id']:a for a in read(ART/'source-wire-audit.json')['cells']}
 rows=[]
 for case in read(DES/'live-cases.json'):
  folder=ART/'public-live'/(case['id']+'-selected');response=folder/'turn-1/response.json.gz'
  if not response.exists():continue
  saved=read(response);body=saved['body'];answer=body.get('answer') or {}
  term=(body.get('assembly') or {}).get('term_agent') or {}
  claims=answer.get('claims',[]) if isinstance(answer,dict) else []
  cited={s for c in claims for s in c.get('source_ids',[])}
  inv=term.get('evidence_inventory',[])
  cited_roots=set()
  for e in inv:
   if e.get('source_id') in cited:
    for sc in e.get('available_scopes',[]):
     if sc.get('delivered_complete'):
      for b in sc.get('block_ids',[]):
       r=block_root(e['document_id'],b)
       if r:cited_roots.add((e['document_id'],r))
  scope=set(read(folder/'binding.json')['scope'])
  acquired={(d,str(u)) for d,u in audit[case['id']]['acquired_articles']}
  g=grades[case['id']];targets=[]
  for t in g['targets']:
   label=t.get('article') or ''
   cur=[d for d,n in names.items() if n==t.get('law') and d in scope]  # same law name exists in other teams' documents
   did=next((d for d in cur if d==t.get('doc_id')),cur[0] if cur else None)
   art=article_root(did,label,t.get('coordinate_scope')) if did and label else None
   targets.append({'law':t.get('law'),'article':label,'coordinate_key':t.get('coordinate_key'),'role':t.get('role'),
                   'current_document_id':did,'registry_document_current':did==t.get('doc_id'),
                   'article_found':art is not None,'acquired':(did,art) in acquired if art else False,'cited':(did,art) in cited_roots if art else False})
  reply=term.get('guided_reply') or {};unread=reply.get('unread_connections') or []
  text=answer.get('text','') if isinstance(answer,dict) else str(answer)
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
  result=read(folder/'turn-1/result.json') if (folder/'turn-1/result.json').exists() else {}
  req=[x for x in targets if x['role']=='required']
  rows.append({'case_id':case['id'],'question':case['steps'][0]['question'],'reference_answer':g['reference_answer'],'answer':text,'http_status':saved['http_status'],
   'request_seconds':result.get('request_seconds'),'claims':len(claims),'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),
   'physical_calls':len(calls),'unknown':sum(c['status'] in ('unknown','started') for c in calls),'response_path':str(response.relative_to(ROOT)),'response_sha256':sha(response),
   'targets':targets,'required_acquired':sum(x['acquired'] for x in req),'required_cited':sum(x['cited'] for x in req),'required_total':len(req),
   'registry_version_differs':any(not x['registry_document_current'] for x in req),
   'acquired_articles':[names.get(d,d)+' '+(units(d).get(str(u),{}).get('surface') or str(u)) for d,u in sorted(acquired)],
   'same_section_reads':[e.get('reason') for e in inv if SECTION_MARK in str(e.get('reason',''))],
   'unread':{'total':reply.get('unread_connection_total'),'shown':len(unread),'answer_has_unread_section':'확인하지 않은 연결 조문' in text,
             'model_reason':sum(u.get('reason_origin')=='MODEL_NOTE' for u in unread),
             'by_reason':dict(__import__('collections').Counter(f"{u.get('relation')}:{u.get('reason_code')}" for u in unread))}})
 put(ART/'review-input.json',{'rows':rows,'reference_input_is_offline_only':True,'semantic_grades_automatically_generated':False})
 return rows

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--brief',action='store_true');a=p.parse_args()
 for r in collect():
  if a.brief:r={k:r[k] for k in ('case_id','claims','needs_guidance','required_acquired','required_cited','required_total','registry_version_differs','physical_calls')}|{'section_reads':len(r['same_section_reads']),'unread_shown':r['unread']['shown']}
  print(json.dumps(r,ensure_ascii=False))
