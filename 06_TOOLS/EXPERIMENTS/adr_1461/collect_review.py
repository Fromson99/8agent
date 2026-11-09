"""Offline CM review collection (reference answers never enter product input).

Required targets are matched by law name + article coordinate on the current generation (same
dataset as the Oracle Gold publication). Acquired articles come from the response's evidence
inventory paths ("… > 상법 제341조의4") and cited articles from claims' source IDs."""
from common import *
import sqlite3,argparse,re
rel=read(DES/'baseline.json')['release'];db=sqlite3.connect((ROOT/rel['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
names={d:n.split(' > ')[-1] for d,n in db.execute('SELECT document_id,name FROM document')}
_units={}
def units(did):
 if did not in _units:
  rows={}
  for uid,parent,raw in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
   v=json.loads(raw);rows[str(uid)]={'parent':None if parent is None else str(parent),'surface':v.get('surface') or '','family':v.get('family')}
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
 hits=[uid for uid,u in units(did).items() if u['family']=='kr_article' and u['surface'].replace(' ','')==label.replace(' ','')]
 want=str(scope or 'body')!='body';hits=[h for h in hits if _in_addenda(did,h)==want] or hits
 return sorted(hits,key=lambda h:int(h) if h.isdigit() else 0)[0] if hits else None
ART_RE=re.compile(r'(제\d+조(?:의\d+)?)')
def path_article(path):
 """'external > financial_team > law > 상법 제341조의4 ② 1.' -> ('상법','제341조의4')."""
 tail=str(path or '').split(' > ')[-1];m=ART_RE.search(tail)
 return (tail[:m.start()].strip(),m.group(1)) if m else (tail.strip(),None)

def collect():
 grades={g['id']:g for g in read(DES/'grading-only.json')}
 audit={a['case_id']:a for a in read(ART/'source-wire-audit.json')['cells']} if (ART/'source-wire-audit.json').exists() else {}
 rows=[]
 for case in read(DES/'live-cases.json'):
  folder=ART/'public-live'/(case['id']+'-candidate');response=folder/'turn-1/response.json.gz'
  if not response.exists():continue
  saved=read(response);body=saved['body'];answer=body.get('answer') or {};term=(body.get('assembly') or {}).get('term_agent') or {}
  claims=answer.get('claims',[]) if isinstance(answer,dict) else [];cited={s for c in claims for s in c.get('source_ids',[])}
  inv=term.get('evidence_inventory',[])
  acquired={(e.get('document_id'),)+path_article(e.get('path')) for e in inv if e.get('availability')=='ACQUIRED' or e.get('status')=='READ'}
  cited_arts={(e.get('document_id'),)+path_article(e.get('path')) for e in inv if e.get('source_id') in cited}
  scope=set(read(folder/'binding.json')['scope']);g=grades[case['id']];targets=[]
  for t in g['targets']:
   label=t.get('article') or '';cur=[d for d,n in names.items() if n==t.get('law') and d in scope]
   did=next((d for d in cur if d==t.get('doc_id')),cur[0] if cur else None)
   art=article_root(did,label,t.get('coordinate_scope')) if did and label else None
   norm=label.replace(' ','')
   targets.append({'law':t.get('law'),'article':label,'role':t.get('role'),'current_document_id':did,'article_found':art is not None,
    'acquired':any(d==did and (a or '').replace(' ','')==norm for d,_,a in acquired),'cited':any(d==did and (a or '').replace(' ','')==norm for d,_,a in cited_arts)})
  reply=term.get('guided_reply') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer)
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else [];result=read(folder/'turn-1/result.json') if (folder/'turn-1/result.json').exists() else {}
  req=[x for x in targets if x['role']=='required']
  rows.append({'case_id':case['id'],'question':case['steps'][0]['question'],'reference_answer':g['reference_answer'],'answer':text,'http_status':saved['http_status'],
   'request_seconds':result.get('request_seconds'),'claims':len(claims),'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),
   'physical_calls':len(calls),'unknown':sum(c['status'] in ('unknown','started') for c in calls),'sql_calls':result.get('sql_calls'),'embedding_calls':result.get('embedding_calls'),
   'named_article_lookup':result.get('named_article_lookup'),'proposed_reads':result.get('proposed_reads'),'reference_normalizations':result.get('reference_normalizations'),
   'targets':targets,'required_acquired':sum(x['acquired'] for x in req),'required_cited':sum(x['cited'] for x in req),'required_total':len(req),
   'acquired_articles':sorted(f"{names.get(d,n)} {a or ''}".strip() for d,n,a in acquired),'main161':g.get('main161'),
   'unread':{'total':reply.get('unread_connection_total'),'shown':len(reply.get('unread_connections') or []),'answer_has_unread_section':'확인하지 않은 연결 조문' in text}})
 put(ART/'review-input.json',{'rows':rows,'reference_input_is_offline_only':True,'semantic_grades_automatically_generated':False})
 return rows

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--brief',action='store_true');a=p.parse_args()
 for r in collect():
  if a.brief:r={k:r[k] for k in ('case_id','http_status','claims','needs_guidance','required_acquired','required_cited','required_total','physical_calls','sql_calls','embedding_calls','named_article_lookup')}
  print(json.dumps(r,ensure_ascii=False))
